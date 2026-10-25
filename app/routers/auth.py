from datetime import timedelta
from sqlite3 import IntegrityError
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
import structlog


from app.core.deps import CurrentUser, OptionalUser, SessionDep
from app.models import User
from app.core import security
from app.core.config import settings
from app.schemas.auth import CurrentUserInfoResponse, NewUserCreate, Token


logger = structlog.get_logger()


router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=CurrentUserInfoResponse)
async def read_users_me(request: Request, current_user: CurrentUser):
    return current_user


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    response: Response,
    db: SessionDep,
    current_user: OptionalUser,
):
    """ Login endpoint """


    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )
    # check if user with this phone exists, then check if password is correct
    result = await db.execute(
        select(User).where(func.lower(User.username) == form_data.username.lower())
    )

    user = result.scalars().first()

    if not user or not security.verify_password(form_data.password, user.password_hash):
        logger.warning("Login failed", email=form_data.username)
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail="Wrong Username or Password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # if both are correct then generate a JWT token (access token + refresh token) and return it with Token model
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.generate_access_token(
        data = {
            "sub": str(user.id),
        },
        expires_delta= access_token_expires
    )

    logger.info("Login successful", user_id=user.id, username=user.username)

    return Token(access_token= access_token, token_type='bearer')





@router.post("/register", status_code=status.HTTP_201_CREATED)
async def create_new_user(
    request: Request,
    new_user: NewUserCreate,
    db: SessionDep,
    current_user: OptionalUser
):
    # check user is not logged in
    if current_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already logged in.",
        )
    
    # check username and phone uniqueness
    normalized_username = new_user.username.lower()
    user_result = await db.execute(
        select(User.username)
        .where(
            (func.lower(User.username) == normalized_username)
        )
    )

    existing_user = user_result.first()

    if existing_user:
        if existing_user.username.lower() == normalized_username:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")

    # hash password
    password_hash = security.hash_password(new_user.password)

    user = User(
        username = normalized_username,
        name = new_user.name,
        password_hash = password_hash
    )


    db.add(user)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("Registration failed", username=normalized_username, reason="duplicate")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or phone number already registered",
        )

    await db.refresh(user)
    logger.info("User registered", user_id=user.id, username=user.username)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "Registration successful. Please login into your account."},
    )
