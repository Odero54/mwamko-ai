from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)


class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    id_number = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=True)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    county = Column(String, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class EmergencyCases(Base):
    __tablename__ = "emergency_cases"

    case_id = Column(Integer, primary_key=True, index=True)
    village = Column(String, nullable=False)
    disaster_type = Column(String, nullable=False)
    severity = Column(String, nullable=False, index=True)
    description = Column(String)
    status = Column(String, default="PENDING", nullable=False, index=True)
    assigned_team_id = Column(Integer, nullable=True)
    reported_by = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    location = Column(String, nullable=False)


class Routes(Base):
    __tablename__ = "routes"
    route_id = Column(Integer, primary_key=True, index=True)
    status = Column(String, nullable=False)
    total_cost = Column(Float, nullable=True)
    optimized_sequence = Column(JSON, nullable=True)
    route_segments = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class ArchivedRoutes(Base):
    __tablename__ = "archived_routes"

    archive_id = Column(Integer, primary_key=True, index=True)
    original_route_id = Column(Integer, nullable=False)
    route_segments = Column(JSON, nullable=False)
    total_cost = Column(Float, nullable=False)
    total_segments = Column(Integer, nullable=False)
    case_ids = Column(JSON, nullable=False)  # Store list of case IDs
    disaster_types = Column(JSON, nullable=False)  # Store list of disaster types
    disaster_descriptions = Column(JSON, nullable=False)  # Store list of descriptions
    resolved_by = Column(String, nullable=False)  # User who resolved the cases
    archived_at = Column(DateTime, default=func.now(), nullable=False)
    archived_by = Column(Integer, nullable=False)  # User ID who archived the route


class RescueVehicles(Base):
    __tablename__ = "rescue_vehicles"

    vehicle_id = Column(Integer, primary_key=True, index=True)
    registration_plate = Column(String, unique=True, index=True, nullable=False)
    vehicle_type = Column(String, unique=True, index=True, nullable=False)
    current_status = Column(String, default="AVAILABLE", nullable=False, index=True)
    current_occupancy = Column(Integer, default=0, nullable=False, index=True)
    last_update_ts = Column(DateTime, default=func.now(), nullable=False)
    current_location = Column(String, nullable=False)


class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=False)
    last_name = Column(String, nullable=False)
    id_number = Column(String, nullable=False)
    county = Column(String, nullable=False)
    phone_number = Column(String, nullable=True)
    role = Column(String, nullable=True)  # Can be assigned later by coordinator
    token = Column(String, unique=True, index=True, nullable=False)
    invited_by = Column(Integer, nullable=False)  # User ID of the County Coordinator
    status = Column(
        String, default="PENDING", nullable=False
    )  # PENDING, ACCEPTED, EXPIRED
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    accepted_at = Column(DateTime, nullable=True)
