from datetime import timedelta, datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker
from starlette import status
from pydantic import BaseModel, EmailStr
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import jwt, JWTError

from database import get_db, SessionLocal
from models import Users
from config import settings

router = APIRouter(
    prefix='/auth',
    tags=['auth']
)

SECRET_KEY = settings.JWT_SECRET_KEY
ALGORITHM = settings.JWT_ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='auth/token')


class CreateUserRequest(BaseModel):
    """Data Model for creating a new user."""
    email: EmailStr
    first_name: str
    last_name: str
    id_number: str
    county: str
    password: str
    role: str
    phone_number: str


class Token(BaseModel):
    """Response model for a successful login."""
    access_token: str
    token_type: str


# Dependency Injection
db_dependency = Annotated[Session, Depends(get_db)]

# ================Utility Functions=====================
def authenticate_user(email: str, password: str, db: Session):
    """
    Authenticates a user based on email (or username) and password.
    """
    user = db.query(Users).filter(Users.email == email).first()
    
    if not user:
        return False
    
    safe_password = password[:72]
    if not bcrypt_context.verify(safe_password, user.hashed_password):
        return False
    return user

def create_access_token(email: str, user_id: int, county: str, role: str, expires_delta:timedelta):
    """Generates a JWT token containing user identity and authorization data."""
    # Use email as the 'subject' claim (sub) for token identification
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
    

# ================Endpoints=====================

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def create_user(
    db: db_dependency, 
    create_user_request: CreateUserRequest):
    """Endpoint for user registration."""
    
    # Check if a user with the same email or ID number already exists
    if db.query(Users).filter((Users.email == create_user_request.email) | 
                              (Users.id_number == create_user_request.id_number)).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email or ID number already exists."
        )

    # Use email as the username for simplicity in the current model
    username_to_use = create_user_request.email

    # Truncate password to the first 72 characters ---
    # This prevents the "ValueError: password cannot be longer than 72 bytes" error.
    safe_password_to_hash = create_user_request.password[:72]
    
    create_user_model = Users(
        username=username_to_use,
        email=create_user_request.email,
        first_name=create_user_request.first_name,
        last_name=create_user_request.last_name,
        phone_number=create_user_request.phone_number,
        id_number=create_user_request.id_number,
        county=create_user_request.county,
        role=create_user_request.role,
        hashed_password=bcrypt_context.hash(safe_password_to_hash), 
        is_active=True
    )

    db.add(create_user_model)
    db.commit()
    
    return {"message": f"User {create_user_request.email} successfully registered."}

@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], 
                                 db: db_dependency):
    """
    Handles user login and generates a JWT access token.
    """
    # form_data.username will contain the user's email submitted in the login form
    user = authenticate_user(form_data.username, form_data.password, db)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail='Incorrect email or password.',
                                headers={"WWW-Authenticate": "Bearer"})
    
    # Use the expiration time from settings
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    token = create_access_token(
        email=user.email, 
        user_id=user.id, 
        county=user.county, 
        role=user.role, 
        expires_delta=access_token_expires
    )
    
    return {'access_token': token, 'token_type': 'bearer'}