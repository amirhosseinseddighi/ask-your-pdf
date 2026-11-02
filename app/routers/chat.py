from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from pydantic import Field
import structlog

from app.core.deps import CurrentUser, LLMClient, SessionDep
from app.helpers.chat_and_project_helpers import (
    check_chat_exists_and_belong_to_the_user, 
    check_project_exists_and_belong_to_the_user
)
from app.models import ChatSession
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse, CreateChatSessionRequest, CreateChatSessionResponse
from app.services.chat_service import chat_service


logger = structlog.get_logger()


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




@router.post("/{chat_id}", response_model=ChatMessageResponse)
async def do_chat(
    current_user: CurrentUser,
    chat_id: UUID,
    chat_request: ChatMessageRequest,
    llm_client: LLMClient,
):
    chat_session = await check_chat_exists_and_belong_to_the_user(chat_id, current_user.id)
    if not chat_session:

        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    try:
        answer = await chat_service.ask(
            session_id=chat_session.id,
            project_id=chat_session.project_id,
            user_query=chat_request.message,
            client=llm_client,
        )
    except RateLimitError:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Service is busy, try again shortly")
    except (APITimeoutError, APIConnectionError):
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, detail="The AI service timed out")
    except APIStatusError:
        logger.exception("OpenAI API error")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="The AI service returned an error")

    return ChatMessageResponse(answer=answer)

    

