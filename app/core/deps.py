from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from openai import AsyncOpenAI, OpenAI
from sqlalchemy import select
import structlog

from app.core.database import AsyncSessionLocal, AsyncSession
from app.core.security import oauth2_scheme,oauth2_scheme_optional , verify_access_token
from app.models import Documents, Project, User

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session




async def get_current_user(
        token: Annotated[str, Depends(oauth2_scheme)],
        db: Annotated[AsyncSession, Depends(get_db)]
):
    user_id = verify_access_token(token=token)
    if not user_id:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Unauthorized User", 
            headers = {"WWW-Authenticate": "Bearer"}
        )
    
    try:
        user_id_int = int(user_id)

    except (TypeError, ValueError):
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED, 
            detail = "Invalid or expired access token", 
            headers = {"WWW-Authenticate": "Bearer"}
        )
    
    
    result = await db.execute(
        select(User).where(User.id == user_id_int)
    )

    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Unauthorized User",
            headers = {"WWW-Authenticate": "Bearer"}
        )

    structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


async def get_optional_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[User]:
    """return authenticated User if a valid token is provided, otherwise None."""
    if not token:
        return None
    
    user_id = verify_access_token(token=token)
    if not user_id:
        return None

    try:
        user_id_int = int(user_id)
    except (TypeError, ValueError):
        return None

    result = await db.execute(
        select(User).where(User.id == user_id_int)
    )
    user = result.scalars().first()
    if user is not None:
        structlog.contextvars.bind_contextvars(user_id=user.id)
    return user


async def get_ai_client():
    from app.main import app
    return app.state.llm_client


async def get_owned_project(
    project_id: int, db: "SessionDep", current_user: "CurrentUser"
) -> Project:
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project



async def get_owned_document(
    project_id: int, document_id: int, db: "SessionDep", current_user: "CurrentUser"
) -> Documents:
    """Use this for GET/DELETE /{project_id}/documents/{document_id}."""
    doc = await db.scalar(
        select(Documents)
        .join(Project, Project.id == Documents.project_id)
        .where(
            Documents.id == document_id,
            Documents.project_id == project_id,
            Project.user_id == current_user.id,
        )
    )
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc




CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[Optional[User], Depends(get_optional_current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_db)]
LLMClient = Annotated[AsyncOpenAI, Depends(get_ai_client)]
OwnedProject = Annotated[Project, Depends(get_owned_project)]
OwnedDocument = Annotated[Documents, Depends(get_owned_document)]
