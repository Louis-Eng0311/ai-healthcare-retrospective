from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RequesterRole(StrEnum):
    PATIENT = "PATIENT"
    CAREGIVER = "CAREGIVER"
    ADMIN = "ADMIN"


# 세션 생성 요청
class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: int = Field(..., ge=1, description="대화 대상 환자 ID")
    mode: str = Field(default="general", min_length=1, max_length=30)


# 세션 생성 응답 data
class ChatSessionCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(ge=1)
    patient_id: int = Field(ge=1)
    mode: str
    created_at: datetime


# 세션 생성 응답
class ChatSessionCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ChatSessionCreateData


# 메시지 생성 요청
class ChatMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(..., min_length=1, max_length=2000)


# 메시지 아이템
class ChatMessageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: int = Field(ge=1)
    role: str
    content: str
    status: str = "completed"
    error_message: str | None = None
    is_emergency: bool = False
    emergency_message: str | None = None
    disclaimer: str | None = None
    created_at: datetime


# 메시지 생성 응답 data
class ChatMessageCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(ge=1)
    user_message: ChatMessageItem
    assistant_message: ChatMessageItem


# 메시지 생성 응답
class ChatMessageCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ChatMessageCreateData


# 메시지 목록 응답 data
class ChatMessageListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int = Field(ge=1)
    items: list[ChatMessageItem]
    total: int = Field(ge=0)


# 메시지 목록 응답
class ChatMessageListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ChatMessageListData


class ChatFeedbackCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_message_id: int = Field(..., ge=1)
    helpful: bool
    feedback_type: str | None = Field(default=None, max_length=50)
    comment: str | None = Field(default=None, max_length=1000)


class ChatFeedbackCreateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: int = Field(ge=1)
    session_id: int = Field(ge=1)
    assistant_message_id: int = Field(ge=1)
    helpful: bool
    feedback_type: str | None = None
    comment: str | None = None
    created_at: datetime


class ChatFeedbackCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: ChatFeedbackCreateData
