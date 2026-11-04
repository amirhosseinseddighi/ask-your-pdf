import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import Field
from sqlalchemy import delete, select
import structlog

from app.core.deps import CurrentUser, LLMClient, SessionDep
from app.helpers.chat_and_project_helpers import (
    check_chat_exists_and_belong_to_the_user, 
    check_project_exists_and_belong_to_the_user
)
from app.models import ChatSession
from app.schemas.chat import ChatMessageRequest, ChatSessionResponse, CreateChatSessionRequest, CreateChatSessionResponse, UpdateChatSessionRequest
from app.services.chat_service import chat_service


logger = structlog.get_logger()


# ========== HELPERS ==============
def sse(event: dict):
    return f"data: {json.dumps(event)}\n\n"


router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/creating", response_model=CreateChatSessionResponse)
async def create_chat_session(
    current_user: CurrentUser,
    create_chat_request: CreateChatSessionRequest,
    db: SessionDep
):

    project_id = create_chat_request.project_id

    project = await check_project_exists_and_belong_to_the_user(project_id, current_user.id)
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    chat_session = ChatSession(
        user_id=current_user.id,
        project_id=project.id
    )

    db.add(chat_session)
    await db.commit()
    await db.refresh(chat_session)
    return CreateChatSessionResponse(chat_session_id=chat_session.id)
    

@router.get("/{chat_id}")
async def get_chat_history(
    current_user: CurrentUser,
    chat_id: UUID,
):
    chat = await check_chat_exists_and_belong_to_the_user(chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found"
        )

    history = await chat_service.get_chat_session_history(chat.id)
    return history




@router.post("/{chat_id}")
async def do_chat(
    current_user: CurrentUser,
    chat_id: UUID,
    chat_request: ChatMessageRequest,
    llm_client: LLMClient,
):
    chat_session = await check_chat_exists_and_belong_to_the_user(chat_id, current_user.id)
    if not chat_session:

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")


    async def event_generator():
        try:
            async for answer in chat_service.ask_stream(
                session_id=chat_session.id,
                project_id=chat_session.project_id,
                user_query=chat_request.message,
                client=llm_client,
            ):
                yield sse(answer)
        except RateLimitError:
            yield sse({"type": "error", "content": "Service is busy, try again shortly"})
        except (APITimeoutError, APIConnectionError):
            yield sse({"type": "error", "content": "The AI service timed out"})
        except APIStatusError:
            logger.exception("LLM API error")
            yield sse({"type": "error", "content": "The AI service returned an error"})
        except Exception:
            logger.exception("Unexpected error while streaming")
            yield sse({"type": "error", "content": "Something went wrong"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )

    

@router.patch("/{chat_id}", response_model=ChatSessionResponse)
async def update_chat_title(
    current_user: CurrentUser,
    chat_id: UUID,
    body: UpdateChatSessionRequest,
    db: SessionDep,
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == chat_id,
            ChatSession.user_id == current_user.id,
        )
    )
    chat_session = result.scalar_one_or_none()
    if not chat_session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    chat_session.title = body.title
    await db.commit()
    await db.refresh(chat_session)
    return chat_session


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    current_user: CurrentUser,
    chat_id: UUID,
    db: SessionDep,
):
    result = await db.execute(
        delete(ChatSession)
        .where(
            ChatSession.id == chat_id,
            ChatSession.user_id == current_user.id,
        )
        .returning(ChatSession.id)
    )
    if result.scalar_one_or_none() is None:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    await db.commit()