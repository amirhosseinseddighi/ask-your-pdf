from datetime import UTC, datetime, timedelta
import hashlib

from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from app.core.config import settings
import jwt
import secrets




password_hash = PasswordHash.recommended()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False
)



# ========= HELPER ============

def hash_password(plain_password: str) -> str:
    return password_hash.hash(plain_password)



def verify_password(plain_password: str, hash_password: str) -> bool:
    return password_hash.verify(plain_password, hash_password)



def generate_access_token(data: dict, expires_delta: timedelta | None = None):
    """ Create a JWT Token """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)


    # add expire date to JSON data
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode, 
        settings.JWT_SECRET.get_secret_value(), 
        settings.JWT_ALGORITHM
    )

    return encoded_jwt

def verify_access_token(token: str) -> str | None:
    """ Verify a JWT access token and return the subject(user id) if valid. """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]}
        )
    
    except jwt.InvalidTokenError:
        return None

    else:
        return payload.get("sub")

def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)

def hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
