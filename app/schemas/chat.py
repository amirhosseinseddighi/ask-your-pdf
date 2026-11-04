
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CreateChatSessionRequest(BaseModel):
    project_id: int = Field(description="Project id")


class CreateChatSessionResponse(BaseModel):
    chat_session_id: UUID

class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime


class UpdateChatSessionRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=150)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    created_at: datetime
    updated_at: datetime