from datetime import timedelta, datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from starlette import status
from pydantic import BaseModel, EmailStr, Field
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
import secrets
import uuid
import os
import resend

from mwamko_ai.database import get_db
from mwamko_ai.models import Users, Invite
from mwamko_ai.config import settings

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)

RESEND_API_KEY = settings.RESEND_API_KEY
resend.api_key = RESEND_API_KEY

SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

bcrypt_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto"
)

oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')

# ================Utility Functions=====================
def authenticate_user(email: str, password: str, db: Session):
    """
    Authenticates a user based on email and password.
    Uses bcrypt_sha256, which supports passwords of any length.
    """
    user = db.query(Users).filter(Users.email == email).first()
    
    if not user:
        return False
    
    if not bcrypt_context.verify(password, user.hashed_password):
        return False
    return user

def create_access_token(email: str, user_id: int, county: str, role: str, expires_delta: timedelta):
    """Generates a JWT token containing user identity and authorization data."""
    encode = {'sub': email, 'id': user_id, 'county': county, 'role': role}
    
    expires = datetime.now(timezone.utc) + expires_delta
    encode.update({'exp': expires})
    
    return jwt.encode(encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    """
    FastAPI dependency to decode and validate the JWT token.
    Returns the user payload (id, county, role).
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Claims from the token
        email: str = payload.get('sub')
        user_id: int = payload.get('id')
        county: str = payload.get('county')
        user_role: str = payload.get('role')
        
        if email is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not validate user credentials.')
        
        return {'email': email, 'id': user_id, 'county': county, 'role': user_role}
        
    except JWTError:
        # This catches token expiration, incorrect signature, etc.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Could not validate user credentials.',
                                headers={"WWW-Authenticate": "Bearer"})

# Dependency to get current county coordinator
def get_current_county_coordinator(current_user: Annotated[dict, Depends(get_current_user)]):
    """Dependency to enforce County Coordinator role."""
    if current_user.get('role') != "County Coordinator":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires County Coordinator privileges."
        )
    return current_user

class CreateUserRequest(BaseModel):
    """Data Model for creating a new user (for initial setup)."""
    email: EmailStr
    first_name: str
    last_name: str
    id_number: str
    county: str
    password: str = Field(..., min_length=8, max_length=50)
    role: str
    phone_number: str

class InviteUserRequest(BaseModel):
    """Data Model for inviting a new user."""
    email: EmailStr
    first_name: str
    last_name: str
    id_number: str
    county: str
    phone_number: str

class AcceptInviteRequest(BaseModel):
    """Data Model for accepting an invite."""
    token: str
    password: str = Field(..., min_length=8, max_length=50)

class AssignRoleRequest(BaseModel):
    """Data Model for assigning role to a user."""
    user_id: int
    role: str

class Token(BaseModel):
    """Response model for a successful login."""
    access_token: str
    token_type: str

class InviteResponse(BaseModel):
    """Response model for invite creation."""
    invite_id: int
    email: str
    token: str
    status: str
    expires_at: str

# Dependency Injection
db_dependency = Annotated[Session, Depends(get_db)]

def generate_invite_token() -> str:
    """Generate a unique invite token."""
    return str(uuid.uuid4())

def send_invite_email(email: str, token: str, coordinator_name: str):
    """
    Send invitation email to the user using Resend API.
    """
    invite_link = f"https://mwamko.net/accept-invite?token={token}"
    subject = "Invitation to join Mwamko AI Emergency Response System"

    message = f"""Hello,

    You have been invited by {coordinator_name} to join the Mwamko AI Emergency Response System.

    Please click the link below to complete your registration:
    {invite_link}

    If you did not expect this email, you can safely ignore it.

    Best,

    Mwamko AI Team
    """

    try:
        response = resend.Emails.send({
            "from": "Mwamko AI <noreply@mwamko.net>",
            "to": [email],  
            "subject": subject,
            "text": message,
        })
        print(f"Email sent successfully to {email}. Response: {response}")
        return response
        
    except Exception as e:
        print(f"Email sending failed to {email}:", e)
        return None



    
    # In production, use:
    # await email_service.send_invitation(email, invite_link, coordinator_name)

# ================Endpoints=====================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def create_user(
    db: db_dependency, 
    create_user_request: CreateUserRequest
):
    """
    Initial user registration endpoint.
    This should only be used for the FIRST County Coordinator registration.
    After that, use the invite system.
    """
    # Check if any users already exist
    existing_users = db.query(Users).count()
    
    # If users already exist, this endpoint should not be used
    if existing_users > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use the invite system for new user registration. Contact system administrator."
        )
    
    # Check if a user with the same email or ID number already exists
    if db.query(Users).filter((Users.email == create_user_request.email) | 
                              (Users.id_number == create_user_request.id_number)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email or ID number already exists."
        )

    # Only allow County Coordinator role for initial registration
    if create_user_request.role != "County Coordinator":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Initial registration must be for County Coordinator role."
        )

    # Use email as the username
    username_to_use = create_user_request.email

    hashed_password = bcrypt_context.hash(create_user_request.password)

    create_user_model = Users(
    username=username_to_use,
    email=create_user_request.email,
    first_name=create_user_request.first_name,
    last_name=create_user_request.last_name,
    phone_number=create_user_request.phone_number,
    id_number=create_user_request.id_number,
    county=create_user_request.county,
    role=create_user_request.role,
    hashed_password=hashed_password, 
    is_active=True
    )

    db.add(create_user_model)
    db.commit()
    
    return {
        "message": f"County Coordinator {create_user_request.email} successfully registered.",
        "note": "Use this account to invite other users via /auth/admin/invite endpoint"
    }

@router.post("/admin/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    invite_data: InviteUserRequest,
    background_tasks: BackgroundTasks,
    db: db_dependency,
    coordinator: Annotated[dict, Depends(get_current_county_coordinator)]
):
    """
    County Coordinator invites a user within their county.
    Only County Coordinators can invite users, and only for their county.
    """
    coordinator_county = coordinator['county']
    
    # Validate that the invite is for the coordinator's county
    if invite_data.county != coordinator_county:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You can only invite users within {coordinator_county} county."
        )
    
    # Check if user already exists
    if db.query(Users).filter(
        (Users.email == invite_data.email) | 
        (Users.id_number == invite_data.id_number)
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email or ID number already exists."
        )
    
    # Check if there's already a pending invite for this email
    existing_invite = db.query(Invite).filter(
        Invite.email == invite_data.email,
        Invite.status == 'PENDING'
    ).first()
    
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email."
        )
    
    # Generate invite token and set expiration (24 hours) - ensure timezone awareness
    invite_token = generate_invite_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    
    # Create invite record
    invite = Invite(
        email=invite_data.email,
        first_name=invite_data.first_name,
        last_name=invite_data.last_name,
        id_number=invite_data.id_number,
        county=invite_data.county,
        phone_number=invite_data.phone_number,
        token=invite_token,
        invited_by=coordinator['id'],
        expires_at=expires_at,  # This is now timezone-aware
        status='PENDING'
    )
    
    db.add(invite)
    db.commit()
    db.refresh(invite)
    
    # Send invitation email (in background)
    coordinator_user = db.query(Users).filter(Users.id == coordinator['id']).first()
    coordinator_name = f"{coordinator_user.first_name} {coordinator_user.last_name}"
    
    background_tasks.add_task(send_invite_email, invite_data.email, invite_token, coordinator_name)
    
    return InviteResponse(
        invite_id=invite.id,
        email=invite.email,
        token=invite.token,
        status=invite.status,
        expires_at=invite.expires_at.isoformat()
    )

@router.post("/invite/accept", status_code=status.HTTP_201_CREATED)
async def accept_invite(
    accept_data: AcceptInviteRequest,
    db: db_dependency
):
    """
    User accepts invitation and sets up their password.
    This creates the user in the Users table with 'PENDING' role.
    """
    # Find the invite
    invite = db.query(Invite).filter(
        Invite.token == accept_data.token,
        Invite.status == 'PENDING'
    ).first()
    
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation token."
        )
    
    # Make both datetimes timezone-aware for comparison
    current_time = datetime.now(timezone.utc)
    expires_at_aware = invite.expires_at.replace(tzinfo=timezone.utc) if invite.expires_at.tzinfo is None else invite.expires_at
    
    # Check if invite is expired
    if current_time > expires_at_aware:
        invite.status = 'EXPIRED'
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This invitation has expired."
        )
    
    # Check if user already exists (double-check)
    if db.query(Users).filter(
        (Users.email == invite.email) | 
        (Users.id_number == invite.id_number)
    ).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email or ID number already exists."
        )
    
    # Create the user account (without role initially)
    hashed_password = bcrypt_context.hash(accept_data.password)
    
    user = Users(
        username=invite.email,  # Use email as username
        email=invite.email,
        first_name=invite.first_name,
        last_name=invite.last_name,
        phone_number=invite.phone_number,
        id_number=invite.id_number,
        county=invite.county,
        role='PENDING',  # Default role until assigned by coordinator
        hashed_password=hashed_password,
        is_active=True
    )
    
    db.add(user)
    db.flush()  # Get the user ID without committing
    
    # Update invite status
    invite.status = 'ACCEPTED'
    invite.accepted_at = datetime.now(timezone.utc)
    
    db.commit()
    
    return {
        "message": "Account created successfully. Please wait for role assignment from your County Coordinator.",
        "user_id": user.id,
        "email": user.email,
        "status": "PENDING_ROLE_ASSIGNMENT"
    }

@router.post("/admin/assign-role", status_code=status.HTTP_200_OK)
async def assign_user_role(
    role_data: AssignRoleRequest,
    db: db_dependency,
    coordinator: Annotated[dict, Depends(get_current_county_coordinator)]
):
    """
    County Coordinator assigns a role to a user within their county.
    This updates the Users table with the final role.
    """
    coordinator_county = coordinator['county']
    
    # Get the user
    user = db.query(Users).filter(Users.id == role_data.user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )
    
    # Validate that the user is in the coordinator's county
    if user.county != coordinator_county:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You can only assign roles to users within {coordinator_county} county."
        )
    
    # Validate that user is pending role assignment
    if user.role != 'PENDING':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a role assigned."
        )
    
    # Validate role
    valid_roles = ['Community Manager', 'Rescue Team', 'Driver']
    if role_data.role not in valid_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        )
    
    # Update user role in Users table
    user.role = role_data.role
    db.commit()
    
    return {
        "message": f"Role '{role_data.role}' assigned successfully to {user.first_name} {user.last_name}",
        "user_id": user.id,
        "email": user.email,
        "role": user.role,
        "status": "ACTIVE"
    }

@router.get("/admin/pending-users")
async def get_pending_users(
    db: db_dependency,
    coordinator: Annotated[dict, Depends(get_current_county_coordinator)]
):
    """
    Get list of users in the coordinator's county who need role assignment.
    These users are already in the Users table with role='PENDING'.
    """
    coordinator_county = coordinator['county']
    
    pending_users = db.query(Users).filter(
        Users.county == coordinator_county,
        Users.role == 'PENDING'
    ).all()
    
    result = []
    for user in pending_users:
        user_data = {
            "user_id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "id_number": user.id_number,
            "phone_number": user.phone_number,
            "county": user.county,
        }
        
        # Safely handle created_at field
        if hasattr(user, 'created_at') and user.created_at:
            user_data["created_at"] = user.created_at.isoformat()
        else:
            user_data["created_at"] = None
            
        result.append(user_data)
    
    return result

@router.get("/admin/invites")
async def get_invites(
    db: db_dependency,
    coordinator: Annotated[dict, Depends(get_current_county_coordinator)]
):
    """
    Get all invites sent by the coordinator.
    """
    invites = db.query(Invite).filter(
        Invite.invited_by == coordinator['id']
    ).order_by(Invite.created_at.desc()).all()
    
    return [
        {
            "invite_id": invite.id,
            "email": invite.email,
            "first_name": invite.first_name,
            "last_name": invite.last_name,
            "status": invite.status,
            "created_at": invite.created_at.isoformat(),
            "expires_at": invite.expires_at.isoformat(),
            "accepted_at": invite.accepted_at.isoformat() if invite.accepted_at else None,
            "user_status": "CREATED" if invite.status == 'ACCEPTED' else "PENDING"
        }
        for invite in invites
    ]

@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
    db: db_dependency
):
    """
    Handles user login and generates a JWT access token.
    """
    user = authenticate_user(form_data.username, form_data.password, db)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect email or password.',
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Check if user has been assigned a role
    if user.role == 'PENDING':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Your account is pending role assignment. Please contact your County Coordinator.'
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    token = create_access_token(
        email=user.email, 
        user_id=user.id, 
        county=user.county, 
        role=user.role, 
        expires_delta=access_token_expires
    )
    
    return {'access_token': token, 'token_type': 'bearer'}