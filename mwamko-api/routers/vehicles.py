from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone

from database import get_db
from routers.auth import get_current_user
from models import RescueVehicles

router = APIRouter(
    prefix="/vehicles",
    tags=["Resource Management - Vehicles"]
)

# Pydantic Models
class VehicleBase(BaseModel):
    registration_plate: str
    vehicle_type: str
    current_status: str = "AVAILABLE"
    current_occupancy: int = 0
    current_location: str

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(BaseModel):
    current_status: Optional[str] = None
    current_occupancy: Optional[int] = None
    current_location: Optional[str] = None

class VehicleResponse(VehicleBase):
    vehicle_id: int
    last_update_ts: str

    class Config:
        from_attributes = True

# Dependency to check if user has resource management permissions
def get_resource_manager(current_user: Annotated[dict, Depends(get_current_user)]):
    """Dependency to enforce resource management permissions."""
    allowed_roles = ['County Coordinator', 'Community Manager', 'Rescue Team']
    if current_user.get('role') not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to manage vehicles."
        )
    return current_user

# Endpoints

@router.post("/", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    vehicle_data: VehicleCreate,
    user: Annotated[dict, Depends(get_resource_manager)],  # Fixed: moved before db
    db: Session = Depends(get_db)
):
    """
    Create a new rescue vehicle.
    Available to: County Coordinator, Community Manager, Rescue Team
    """
    # Check if vehicle with same registration plate already exists
    existing_vehicle = db.query(RescueVehicles).filter(
        RescueVehicles.registration_plate == vehicle_data.registration_plate
    ).first()
    
    if existing_vehicle:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this registration plate already exists."
        )
    
    # Check if vehicle type already exists (if unique constraint is desired)
    existing_type = db.query(RescueVehicles).filter(
        RescueVehicles.vehicle_type == vehicle_data.vehicle_type
    ).first()
    
    if existing_type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A vehicle with this type already exists."
        )
    
    # Validate status
    valid_statuses = ['AVAILABLE', 'ON_MISSION', 'MAINTENANCE', 'OUT_OF_SERVICE']
    if vehicle_data.current_status not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    # Validate occupancy
    if vehicle_data.current_occupancy < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Occupancy cannot be negative."
        )
    
    # Create new vehicle
    new_vehicle = RescueVehicles(
        registration_plate=vehicle_data.registration_plate,
        vehicle_type=vehicle_data.vehicle_type,
        current_status=vehicle_data.current_status,
        current_occupancy=vehicle_data.current_occupancy,
        current_location=vehicle_data.current_location
    )
    
    db.add(new_vehicle)
    db.commit()
    db.refresh(new_vehicle)
    
    return VehicleResponse(
        vehicle_id=new_vehicle.vehicle_id,
        registration_plate=new_vehicle.registration_plate,
        vehicle_type=new_vehicle.vehicle_type,
        current_status=new_vehicle.current_status,
        current_occupancy=new_vehicle.current_occupancy,
        current_location=new_vehicle.current_location,
        last_update_ts=new_vehicle.last_update_ts.isoformat()
    )

@router.get("/", response_model=List[VehicleResponse])
async def get_vehicles(
    user: Annotated[dict, Depends(get_current_user)],  # Fixed: moved before db
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    vehicle_type: Optional[str] = Query(None, description="Filter by vehicle type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get all rescue vehicles with optional filtering.
    Available to: All authenticated users
    """
    query = db.query(RescueVehicles)
    
    # Apply filters
    if status_filter:
        query = query.filter(RescueVehicles.current_status == status_filter)
    
    if vehicle_type:
        query = query.filter(RescueVehicles.vehicle_type == vehicle_type)
    
    vehicles = query.order_by(RescueVehicles.last_update_ts.desc()).offset(skip).limit(limit).all()
    
    return [
        VehicleResponse(
            vehicle_id=vehicle.vehicle_id,
            registration_plate=vehicle.registration_plate,
            vehicle_type=vehicle.vehicle_type,
            current_status=vehicle.current_status,
            current_occupancy=vehicle.current_occupancy,
            current_location=vehicle.current_location,
            last_update_ts=vehicle.last_update_ts.isoformat()
        )
        for vehicle in vehicles
    ]

@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(
    vehicle_id: int,
    user: Annotated[dict, Depends(get_current_user)],  # Fixed: moved before db
    db: Session = Depends(get_db)
):
    """
    Get a specific vehicle by ID.
    Available to: All authenticated users
    """
    vehicle = db.query(RescueVehicles).filter(RescueVehicles.vehicle_id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    
    return VehicleResponse(
        vehicle_id=vehicle.vehicle_id,
        registration_plate=vehicle.registration_plate,
        vehicle_type=vehicle.vehicle_type,
        current_status=vehicle.current_status,
        current_occupancy=vehicle.current_occupancy,
        current_location=vehicle.current_location,
        last_update_ts=vehicle.last_update_ts.isoformat()
    )

@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(
    vehicle_id: int,
    vehicle_update: VehicleUpdate,
    user: Annotated[dict, Depends(get_resource_manager)],  # Fixed: moved before db
    db: Session = Depends(get_db)
):
    """
    Update a vehicle's status, occupancy, or location.
    Available to: County Coordinator, Community Manager, Rescue Team
    """
    vehicle = db.query(RescueVehicles).filter(RescueVehicles.vehicle_id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    
    # Validate status if provided
    if vehicle_update.current_status is not None:
        valid_statuses = ['AVAILABLE', 'ON_MISSION', 'MAINTENANCE', 'OUT_OF_SERVICE']
        if vehicle_update.current_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
    
    # Validate occupancy if provided
    if vehicle_update.current_occupancy is not None:
        if vehicle_update.current_occupancy < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Occupancy cannot be negative."
            )
    
    # Update fields if provided
    update_data = vehicle_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(vehicle, field, value)
    
    # Update timestamp
    vehicle.last_update_ts = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(vehicle)
    
    return VehicleResponse(
        vehicle_id=vehicle.vehicle_id,
        registration_plate=vehicle.registration_plate,
        vehicle_type=vehicle.vehicle_type,
        current_status=vehicle.current_status,
        current_occupancy=vehicle.current_occupancy,
        current_location=vehicle.current_location,
        last_update_ts=vehicle.last_update_ts.isoformat()
    )

@router.get("/status/available", response_model=List[VehicleResponse])
async def get_available_vehicles(
    user: Annotated[dict, Depends(get_current_user)],  # Fixed: moved before db
    db: Session = Depends(get_db),
    vehicle_type: Optional[str] = Query(None, description="Filter by vehicle type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get all available vehicles (status = 'AVAILABLE').
    Available to: All authenticated users
    """
    query = db.query(RescueVehicles).filter(RescueVehicles.current_status == 'AVAILABLE')
    
    if vehicle_type:
        query = query.filter(RescueVehicles.vehicle_type == vehicle_type)
    
    vehicles = query.order_by(RescueVehicles.last_update_ts.desc()).offset(skip).limit(limit).all()
    
    return [
        VehicleResponse(
            vehicle_id=vehicle.vehicle_id,
            registration_plate=vehicle.registration_plate,
            vehicle_type=vehicle.vehicle_type,
            current_status=vehicle.current_status,
            current_occupancy=vehicle.current_occupancy,
            current_location=vehicle.current_location,
            last_update_ts=vehicle.last_update_ts.isoformat()
        )
        for vehicle in vehicles
    ]

@router.get("/types/distinct")
async def get_vehicle_types(
    user: Annotated[dict, Depends(get_current_user)],  # Fixed: moved before db
    db: Session = Depends(get_db)
):
    """
    Get distinct vehicle types available in the system.
    Available to: All authenticated users
    """
    vehicle_types = db.query(RescueVehicles.vehicle_type).distinct().all()
    return [vehicle_type[0] for vehicle_type in vehicle_types]

@router.get("/status/summary")
async def get_vehicle_status_summary(
    user: Annotated[dict, Depends(get_current_user)],  # Fixed: moved before db
    db: Session = Depends(get_db)
):
    """
    Get a summary of vehicle status counts.
    Available to: All authenticated users
    """
    from sqlalchemy import func
    
    status_counts = db.query(
        RescueVehicles.current_status,
        func.count(RescueVehicles.vehicle_id).label('count')
    ).group_by(RescueVehicles.current_status).all()
    
    return {
        "status_summary": {
            status: count for status, count in status_counts
        },
        "total_vehicles": sum(count for _, count in status_counts)
    }