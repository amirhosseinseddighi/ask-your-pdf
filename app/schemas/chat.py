
from uuid import UUID

from pydantic import BaseModel, Field


class CreateChatSessionRequest(BaseModel):
    project_id: int = Field(description="Project id")


class CreateChatSessionResponse(BaseModel):
    chat_session_id: UUID

class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)