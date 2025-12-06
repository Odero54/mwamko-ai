from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from mwamko_ai.database import get_db
from mwamko_ai.models import EmergencyCases, Users
from mwamko_ai.routers.auth import get_current_user

router = APIRouter(
    prefix='/api/v1',
    tags=['Emergency Case Management']
)


# Pydantic Models for Request/Response
class EmergencyCaseBase(BaseModel):
    village: str
    disaster_type: str
    severity: str
    description: Optional[str] = None
    location: str

class CaseCreate(EmergencyCaseBase):
    pass

class EmergencyCaseUpdate(BaseModel):
    status: Optional[str] = None
    assigned_team_id: Optional[int] = None

class EmergencyCaseResponse(BaseModel):
    case_id: int
    status: str
    assigned_team_id: Optional[int] = None
    reported_by: int
    created_at: datetime
    
    class Config:
        from_attributes = True



# Utility Functions
def can_create_case(user_role: str) -> bool:
    """Check if user role can create cases"""
    return user_role in ['Community Manager', 'County Coordinator']

def can_update_case(user_role: str) -> bool:
    """Check if user role can update cases"""
    return user_role in ['County Coordinator', 'Rescue Team']

def can_view_all_cases(user_role: str) -> bool:
    """Check if user role can view all cases"""
    return user_role in ['Community Manager', 'Rescue Team']


# Endpoints
@router.post("/cases/emergency_cases", response_model=EmergencyCaseResponse, status_code=status.HTTP_201_CREATED)
async def create_emergency_case(
    case_data: CaseCreate, 
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new emergency case.
    Available to: Community Managers, County Coordinators
    """
    if not can_create_case(current_user['role']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to create emergency cases"
        )

    # Verify the user exists in database
    user = db.query(Users).filter(Users.id == current_user['id']).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Create new case
    new_case = EmergencyCases(
        village=case_data.village,
        disaster_type=case_data.disaster_type,
        severity=case_data.severity,
        description=case_data.description,
        location=case_data.location,
        reported_by=current_user['id'],
        status='PENDING'
    )

    db.add(new_case)
    db.commit()
    db.refresh(new_case)
    
    return new_case

@router.get("/cases/emergency_cases", response_model=List[EmergencyCaseResponse])
async def get_emergency_cases(
    db: Session = Depends(get_db), 
    current_user: dict = Depends(get_current_user), 
    status_filter: Optional[str] = Query(None, description="Filter by status (PENDING, IN PROGRESS, RESOLVED)"),
    severity_filter: Optional[str] = Query(None, description="Filter by severity"),
    disaster_type_filter: Optional[str] = Query(None, description="Filter by disaster type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get emergency cases with optional filtering.
    Community Managers: Can view all cases
    County Coordinators: Can view only active (non-RESOLVED) cases
    Rescue Teams: Can view all non-RESOLVED cases
    """
    user_role = current_user['role']
    
    # Base query
    query = db.query(EmergencyCases)
    
    if user_role == 'County Coordinator':
        query = query.filter(EmergencyCases.status != 'RESOLVED')
    elif user_role == 'Rescue Team':
        query = query.filter(EmergencyCases.status != 'RESOLVED')
    
    if status_filter:
        query = query.filter(EmergencyCases.status == status_filter)
    if severity_filter:
        query = query.filter(EmergencyCases.severity == severity_filter)
    if disaster_type_filter:
        query = query.filter(EmergencyCases.disaster_type == disaster_type_filter)
    
    # Order by creation date (newest first) and apply pagination
    cases = query.order_by(EmergencyCases.created_at.desc()).offset(skip).limit(limit).all()
    
    return cases


@router.get("/cases/{case_id}", response_model=EmergencyCaseResponse)
async def get_emergency_case(
    case_id: int,
    db: Session = Depends(get_db),  # FIXED
    current_user: dict = Depends(get_current_user)  # FIXED
):
    """
    Get a specific emergency case by ID.
    Role-based access control applies.
    """
    case = db.query(EmergencyCases).filter(EmergencyCases.case_id == case_id).first()
    
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency case not found"
        )
    
    # Check access permissions
    user_role = current_user['role']
    if user_role == 'County Coordinator' and case.status == 'RESOLVED':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="County Coordinators can only view active cases"
        )
    elif user_role == 'Rescue Team' and case.status == 'RESOLVED':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Rescue Teams can only view non-resolved cases"
        )
    
    return case


@router.put("/cases/{case_id}", response_model=EmergencyCaseResponse)
async def update_emergency_case(
    case_id: int,
    case_update: EmergencyCaseUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an emergency case (status and/or assigned team).
    Available to: County Coordinators, Rescue Teams
    """
    if not can_update_case(current_user['role']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to update emergency cases"
        )
    
    # Get the case
    case = db.query(EmergencyCases).filter(EmergencyCases.case_id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Emergency case not found"
        )
    
    # Rescue Teams can only update cases assigned to them
    if current_user['role'] == 'Rescue Team':
        if case.assigned_team_id != current_user['id']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rescue Teams can only update cases assigned to them"
            )
    
    # Update fields if provided
    update_data = case_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)
    
    # If Rescue Team is updating status to RESOLVED, ensure they're assigned
    if (current_user['role'] == 'Rescue Team' and 
        case_update.status == 'RESOLVED' and 
        case.assigned_team_id != current_user['id']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the assigned rescue team can resolve a case"
        )
    
    db.commit()
    db.refresh(case)
    
    return case

@router.get("/cases/my/reported cases", response_model=List[EmergencyCaseResponse])
async def get_my_reported_cases(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get cases reported by the current user.
    Available to all roles who can create cases.
    """
    if not can_create_case(current_user['role']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to view reported cases"
        )
    
    cases = db.query(EmergencyCases)\
        .filter(EmergencyCases.reported_by == current_user['id'])\
        .order_by(EmergencyCases.created_at.desc())\
        .offset(skip).limit(limit).all()
    
    return cases

@router.get("/cases/team/assigned case", response_model=List[EmergencyCaseResponse])
async def get_assigned_cases(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get cases assigned to the current rescue team.
    Available only to Rescue Teams.
    """
    if current_user['role'] != 'Rescue Team':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Rescue Teams can view assigned cases"
        )
    
    cases = db.query(EmergencyCases)\
        .filter(EmergencyCases.assigned_team_id == current_user['id'])\
        .order_by(EmergencyCases.created_at.desc())\
        .offset(skip).limit(limit).all()
    
    return cases