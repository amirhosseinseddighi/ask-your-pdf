from typing import List
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
import structlog

from app.models import Project
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.core.deps import CurrentUser, SessionDep

logger = structlog.get_logger()

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: ProjectCreate,
    current_user: CurrentUser,
    db: SessionDep,
):
    """Create a new project associated with the authenticated user."""
    logger.info("Creating project", user_id=current_user.id, project_name=project_in.name)
    
    db_project = Project(
        name=project_in.name,
        description=project_in.description,
        user_id=current_user.id,
    )
    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)
    return db_project


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user: CurrentUser,
    db: SessionDep,
    skip: int = 0,
    limit: int = 100,
):
    """List all projects belonging to the authenticated user with pagination."""
    logger.info("Listing projects", user_id=current_user.id, skip=skip, limit=limit)
    
    result = await db.execute(
        select(Project)
        .where(Project.user_id == current_user.id)
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    current_user: CurrentUser,
    db: SessionDep,
):
    """Get a specific project by ID (ensuring user ownership)."""
    logger.info("Fetching project", user_id=current_user.id, project_id=project_id)
    
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_user: CurrentUser,
    db: SessionDep,
):
    """Update an existing project (partial update)."""
    logger.info("Updating project", user_id=current_user.id, project_id=project_id)
    
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    
    if not project:
      raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    
    update_data = project_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: CurrentUser,
    db: SessionDep,
):
    """Delete a project by ID (ensuring user ownership)."""
    logger.info("Deleting project", user_id=current_user.id, project_id=project_id)
    
    result = await db.execute(
        select(Project)
        .where(Project.id == project_id, Project.user_id == current_user.id)
    )
    project = result.scalars().first()
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    
    await db.delete(project)
    await db.commit()
    return None