from typing import Annotated, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from routers.auth import get_current_user
from routers.admin import get_current_county_coordinator
from models import Routes, EmergencyCases, Users


router = APIRouter(
    prefix="/cases",
    tags=["Route Optimization"]
)

class RouteSummary(BaseModel):
    route_id: int
    status: str
    total_cost: float
    optimized_sequence: List[int]
    created_at: str
    total_segments: int

class RouteDetails(BaseModel):
    route_id: int
    status: str
    total_cost: float
    optimized_sequence: List[int]
    route_segments: List[dict]
    created_at: str

class ArchivedRouteResponse(BaseModel):
    archive_id: int
    original_route_id: int
    route_segments: List[dict]
    total_cost: float
    total_segments: int
    case_ids: List[int]
    disaster_types: List[str]
    disaster_descriptions: List[str]
    resolved_by: str
    archived_at: str

class RouteArchive(BaseModel):
    original_route_id: int
    route_segments: List[dict]
    total_cost: float
    total_segments: int
    case_ids: List[int]
    disaster_types: List[str]
    disaster_descriptions: List[str]
    resolved_by: str

@router.get("/route/latest", response_model=RouteSummary)
async def get_latest_route(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves the most recently calculated optimal route and its summary.
    Available to: All Users (County Coordinator, Community Manager, and Rescue Team)
    """
    latest_route = db.query(Routes).order_by(Routes.created_at.desc()).first()
    
    if not latest_route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No routes have been calculated yet"
        )
    
    return RouteSummary(
        route_id=latest_route.route_id,
        status=latest_route.status,
        total_cost=latest_route.total_cost,
        optimized_sequence=latest_route.optimized_sequence,
        created_at=latest_route.created_at.isoformat(),
        total_segments=len(latest_route.route_segments) if latest_route.route_segments else 0
    )

@router.get("/route/{route_id}/details", response_model=RouteDetails)
async def get_route_details(
    route_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieves the full JSON path for a route to display on the map.
    Available to: All Users (County Coordinator, Community Manager, and Rescue Team)
    """
    route = db.query(Routes).filter(Routes.route_id == route_id).first()
    
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found"
        )
    
    return RouteDetails(
        route_id=route.route_id,
        status=route.status,
        total_cost=route.total_cost,
        optimized_sequence=route.optimized_sequence,
        route_segments=route.route_segments,
        created_at=route.created_at.isoformat()
    )


@router.get("/routes/", response_model=List[RouteSummary])
async def get_all_routes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    """
    Get all calculated routes (summary only).
    Available to: All Users
    """
    routes = db.query(Routes).order_by(Routes.created_at.desc()).offset(skip).limit(limit).all()
    
    return [
        RouteSummary(
            route_id=route.route_id,
            status=route.status,
            total_cost=route.total_cost,
            optimized_sequence=route.optimized_sequence,
            created_at=route.created_at.isoformat(),
            total_segments=len(route.route_segments) if route.route_segments else 0
        )
        for route in routes
    ]


# DELETE endpoint for archiving routes
@router.delete("/route/{route_id}/archive", response_model=ArchivedRouteResponse)
async def archive_route(
    route_id: int,
    user: Annotated[dict, Depends(get_current_county_coordinator)],
    db: Session = Depends(get_db)
):
    """
    Archive a route - only allowed when all cases used to compute the route are resolved.
    Only County Coordinators can archive routes.
    """
    # Get the route
    route = db.query(Routes).filter(Routes.route_id == route_id).first()
    if not route:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Route not found"
        )
    
    # Extract case IDs from optimized_sequence (excluding the start node which is usually first)
    # The optimized_sequence contains node IDs, we need to find which cases they belong to
    case_ids = await get_case_ids_from_route(db, route.optimized_sequence)
    
    if not case_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not find cases associated with this route"
        )
    
    # Check if all cases are resolved
    unresolved_cases = db.query(EmergencyCases).filter(
        EmergencyCases.case_id.in_(case_ids),
        EmergencyCases.status != 'RESOLVED'
    ).all()

    if unresolved_cases:
        unresolved_ids = [case.case_id for case in unresolved_cases]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot archive route. The following cases are not resolved: {unresolved_ids}"
        )
    
    # Get case details for archiving
    cases = db.query(EmergencyCases).filter(EmergencyCases.case_id.in_(case_ids)).all()
    
    # Get disaster types and descriptions
    disaster_types = [case.disaster_type for case in cases]
    disaster_descriptions = [case.description for case in cases if case.description]

    # Get the user who resolved the cases (get the latest assigned team or reporter)
    resolved_by_user = await get_resolved_by_user(db, case_ids)

    # Archive the route
    try:
        # Insert into archived_routes table
        archive_query = """
        INSERT INTO archived_routes 
        (original_route_id, route_segments, total_cost, total_segments, case_ids, 
         disaster_types, disaster_descriptions, resolved_by, archived_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING archive_id, archived_at
        """
        
        # Use raw SQL for the archive table
        from database import engine
        with engine.connect() as connection:
            result = connection.execute(
                archive_query,
                (
                    route.route_id,
                    json.dumps(route.route_segments),
                    route.total_cost,
                    len(route.route_segments) if route.route_segments else 0,
                    json.dumps(case_ids),
                    json.dumps(disaster_types),
                    json.dumps(disaster_descriptions),
                    resolved_by_user,
                    user['id']
                )
            )
            archive_result = result.fetchone()
            connection.commit()

        # Delete the original route
        db.delete(route)
        db.commit()

        return ArchivedRouteResponse(
            archive_id=archive_result[0],
            original_route_id=route.route_id,
            route_segments=route.route_segments,
            total_cost=route.total_cost,
            total_segments=len(route.route_segments) if route.route_segments else 0,
            case_ids=case_ids,
            disaster_types=disaster_types,
            disaster_descriptions=disaster_descriptions,
            resolved_by=resolved_by_user,
            archived_at=archive_result[1].isoformat()
        ) 
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive route: {str(e)}"
        )
    
# GET endpoint for archived routes
@router.get("/routes/archived", response_model=List[ArchivedRouteResponse])
async def get_archived_routes(
    user: Annotated[dict, Depends(get_current_user)],
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000)
):
    """
    Get all archived routes.
    Available to: All Users
    """
    # Use SQLAlchemy core instead of raw SQL for better compatibility
    from sqlalchemy import text
    from database import engine
    
    with engine.connect() as connection:
        # Use text() for SQL and proper parameter binding
        query = text("""
            SELECT * FROM archived_routes 
            ORDER BY archived_at DESC 
            OFFSET :skip LIMIT :limit
        """)
        
        result = connection.execute(
            query, 
            {"skip": skip, "limit": limit}
        )
        archived_routes = result.fetchall()

    archived_list = []
    for row in archived_routes:
        archived_list.append(ArchivedRouteResponse(
            archive_id=row[0],
            original_route_id=row[1],
            route_segments=json.loads(row[2]) if row[2] else [],
            total_cost=row[3],
            total_segments=row[4],
            case_ids=json.loads(row[5]) if row[5] else [],
            disaster_types=json.loads(row[6]) if row[6] else [],
            disaster_descriptions=json.loads(row[7]) if row[7] else [],
            resolved_by=row[8],
            archived_at=row[9].isoformat() if row[9] else None
        ))

    return archived_list


# Helper functions
async def get_case_ids_from_route(db: Session, optimized_sequence: List[int]) -> List[int]:
    """Extract case IDs from route's optimized sequence of nodes."""
    if not optimized_sequence:
        return []
    
    # The optimized_sequence contains road network node IDs
    # We need to find which emergency cases are closest to these nodes
    case_ids = []
    
    for node_id in optimized_sequence[1:]:  # Skip the first node (start point)
        # Find cases that have this node as their nearest road node
        case = db.query(EmergencyCases).filter(
            EmergencyCases.location.isnot(None)
        ).first()  # This is simplified - you might need a more complex spatial query
        
        if case and case.case_id not in case_ids:
            case_ids.append(case.case_id)
    
    return case_ids

async def get_resolved_by_user(db: Session, case_ids: List[int]) -> str:
    """Get the name of the user who resolved the cases."""
    if not case_ids:
        return "Unknown"
    
    # Get the most recent case to find who resolved it
    latest_case = db.query(EmergencyCases).filter(
        EmergencyCases.case_id.in_(case_ids)
    ).order_by(EmergencyCases.created_at.desc()).first()
    
    if not latest_case:
        return "Unknown"
    
    # Try to get the assigned team user first, then fall back to the reporter
    user_id = latest_case.assigned_team_id or latest_case.reported_by
    user = db.query(Users).filter(Users.id == user_id).first()
    
    if user:
        return f"{user.first_name} {user.last_name}"
    else:
        return "Unknown User"