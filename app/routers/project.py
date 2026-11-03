import asyncio
from hashlib import sha256
import os
from pathlib import Path
from typing import Annotated, List
import uuid
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
import structlog
from sqlalchemy import select

from app.models import ChatSession, DocumentState, Documents, Project
from app.schemas.chat import ChatSessionResponse
from app.schemas.project import DocumentUploadResponse, ProjectCreate, ProjectResponse, ProjectUpdate
from app.core.deps import CurrentUser, LLMClient, OwnedDocument, OwnedProject, SessionDep
from sqlalchemy import delete as SQLDelete
from app.services.document_service import ingest_document


logger = structlog.get_logger()

# ========== CONSTANTS ===========
TEMP_FILE_DIRECTORY = "/app/tmp/documents/"
CHUNK_SIZE = 1024 * 1024
MAX_DOCUMENT_SIZE = 1024 * 1024 * 20
MAX_DOCUMENTS_PER_PROJECT=10
MAX_FILENAME_LENGTH=200

# make temp files directory
try:
    os.makedirs(os.path.dirname(TEMP_FILE_DIRECTORY), exist_ok=True)
except:
    logger.error("create temp file directory failed")




router = APIRouter(prefix="/projects", tags=["Projects"])


# ============== PROJECT CRUD =============
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



# ======== LIST PROJECT CHATS ===========
@router.get("/{project_id}/chats")
async def get_all_chat_sessions(
    current_user: CurrentUser,
    db: SessionDep,
    project: OwnedProject
):
    req = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .where(ChatSession.project_id == project.id)
    )

    return [
        ChatSessionResponse.model_validate(session) for session in req.scalars().all()
    ]





# ==================== DOCUMENTS ====================
@router.post(
    "/{project_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentUploadResponse,
)
async def upload_document_pdf(
    pdf_document: Annotated[UploadFile, File(description="PDF Document")],
    background_tasks: BackgroundTasks,
    llm_client: LLMClient,
    db: SessionDep,
    project: OwnedProject,
):
    if pdf_document.content_type != "application/pdf":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDFs are allowed")

    if pdf_document.size is not None and pdf_document.size > MAX_DOCUMENT_SIZE:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The PDF is too large")

    doc_count = await db.scalar(
        select(func.count()).select_from(Documents).where(Documents.project_id == project.id)
    )
    if doc_count >= MAX_DOCUMENTS_PER_PROJECT:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document limit reached for this project")

    original_name = Path(pdf_document.filename or "document.pdf").name[:MAX_FILENAME_LENGTH]
    dst_path = Path(TEMP_FILE_DIRECTORY) / f"{uuid.uuid4()}.pdf"
    handed_off = False

    try:
        total_length = 0
        sha = sha256()
        with open(dst_path, "wb") as buffer:
            while chunk := await pdf_document.read(CHUNK_SIZE):
                if total_length == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(
                        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "File is not a valid PDF"
                    )
                total_length += len(chunk)
                if total_length > MAX_DOCUMENT_SIZE:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The PDF is too large")
                sha.update(chunk)
                await asyncio.to_thread(buffer.write, chunk)

        if total_length == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The file is empty")

        document_hash = sha.hexdigest()

        existing_id = await db.scalar(
            select(Documents.id).where(
                Documents.project_id == project.id,
                Documents.content_hash == document_hash,
            )
        )
        if existing_id:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This document was already uploaded to this project",
            )

        new_doc = Documents(
            project_id=project.id,
            filename=original_name,
            temp_path=str(dst_path),
            status=DocumentState.PENDING,
            content_hash=document_hash,
        )
        db.add(new_doc)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="This document was already uploaded to this project",
            )
        await db.refresh(new_doc)

        background_tasks.add_task(
            ingest_document,
            project_id=project.id,
            doc_id=new_doc.id,
            client=llm_client,
            file_path=str(dst_path),
        )
        handed_off = True
        return DocumentUploadResponse(document_id=new_doc.id, status=new_doc.status)

    except HTTPException:
        raise
    except Exception:
        logger.exception("document_upload_failed", project_id=project.id)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Something went wrong. Please try again"
        )
    finally:
        if not handed_off:
            dst_path.unlink(missing_ok=True)

    




@router.delete(
        "/{project_id}/documents/{document_id}", 
        status_code=status.HTTP_204_NO_CONTENT
)
async def delete_document(
    db: SessionDep,
    current_user: CurrentUser,
    project: OwnedProject,
    document: OwnedDocument
):
    """ Delete a document and it's embeddings """
    await db.delete(document)
    await db.commit()
