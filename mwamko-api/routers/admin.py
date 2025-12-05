from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, status

from pydantic import BaseModel  # you also need BaseModel for your input/output schemas

from sqlalchemy.orm import Session  # for db_session dependency

from utils.routing import (
    find_tsp_route,
    get_nodes_from_cases_and_start_point,
    save_route_to_database,
)

from .dependencies import get_current_user
from .database import get_db
from .models import EmergencyCases  # add other models if needed


router = APIRouter(
    prefix="/routes",
    tags=["Route Optimization"],
)


def get_current_county_coordinator(
    current_user: Annotated[dict, Depends(get_current_user)],
):
    """Dependency to enforce County Coordinator role."""
    if current_user.get("role") != "County Coordinator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires County Coordinator privileges.",
        )
    return current_user


class CaseInput(BaseModel):
    """Input model for the route calculation endpoint."""

    case_ids: List[int]
    # GPS coordinate of the starting point (e.g., "38.5569,-3.3968" (lon, lat))
    start_point_gps: str

    class Config:
        schema_extra = {
            "example": {
                "case_ids": [1, 2, 3],
                "start_point_gps": "38.5569,-3.3968",  # longitude,latitude for Taita Taveta
            }
        }


class RouteResponse(BaseModel):
    """Output model for the calculated route."""

    route_id: int
    status: str
    total_segments: int
    total_cost: float
    optimized_sequence: List[int]
    route_segments: List[dict]


def get_psycopg2_connection():
    """Establishes a raw psycopg2 connection using environment config."""
    conn = None
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.cursor_factory = RealDictCursor
        return conn
    except Exception as e:
        print(f"psycopg2 Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not establish raw database connection for routing.",
        )


@router.post("/route/calculate", response_model=RouteResponse)
async def calculate_route(
    input_data: CaseInput,
    user: Annotated[dict, Depends(get_current_county_coordinator)],
    db_session: Annotated[Session, Depends(get_db)],
):
    """
    Calculate optimal route for emergency cases and save to database.
    """
    county = user.get("county")

    if len(input_data.case_ids) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 1 case is required to calculate a route.",
        )

    # Verify cases exist
    case_objects = (
        db_session.query(EmergencyCases)
        .filter(EmergencyCases.case_id.in_(input_data.case_ids))
        .all()
    )

    if len(case_objects) != len(input_data.case_ids):
        found_ids = {c.case_id for c in case_objects}
        missing_ids = [cid for cid in input_data.case_ids if cid not in found_ids]

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case IDs {missing_ids} not found.",
        )

    psycopg_conn = get_psycopg2_connection()
    try:
        # Convert start point to WKT (expecting "lon,lat" format)
        coords = [p.strip() for p in input_data.start_point_gps.split(",")]
        if len(coords) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Start point must be in 'longitude,latitude' format",
            )

        # Validate coordinates are numeric
        try:
            lon = float(coords[0])
            lat = float(coords[1])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Coordinates must be numeric values",
            )

        # Create proper WKT format: POINT(lon lat) - NO COMMA between coordinates
        start_point_wkt = f"POINT({lon} {lat})"

        print(f"Calculating route with start point: {start_point_wkt}")  # Debug log

        # Get nearest road nodes for cases and start point
        node_ids = get_nodes_from_cases_and_start_point(
            psycopg_conn, input_data.case_ids, start_point_wkt
        )

        print(f"Found nodes: {node_ids}")  # Debug log

        if len(node_ids) < 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not find enough road nodes for routing.",
            )

        # Calculate optimal route
        route_segments = find_tsp_route(psycopg_conn, node_ids)

        if not route_segments:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No route could be found connecting all required nodes.",
            )

        total_cost = route_segments[-1]["cumulative_cost"] if route_segments else 0.0

        # Save route to database
        route_id = save_route_to_database(
            psycopg_conn, "calculated", total_cost, node_ids, route_segments
        )

        return RouteResponse(
            route_id=route_id,
            status="calculated",
            total_segments=len(route_segments),
            total_cost=total_cost,
            optimized_sequence=node_ids,
            route_segments=route_segments,
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Critical error during route calculation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during routing: {e}",
        )
    finally:
        if psycopg_conn:
            psycopg_conn.close()
