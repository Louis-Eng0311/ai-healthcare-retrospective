from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.dtos.base import BaseSerializerModel


# 초대 코드 생성 및 응답 - REQ-USER-004
class InviteCodeCreateRequest(BaseModel):
    expires_in_minutes: Annotated[int, Field(default=5, ge=1, le=60 * 24 * 30)]


class InviteCodeCreateResponse(BaseSerializerModel):
    code: str
    expires_at: datetime


# 초대 코드 연동 - REQ-USER-005
class LinkByInviteCodeRequest(BaseModel):
    code: Annotated[str, Field(min_length=4, max_length=100)]


class LinkByInviteCodeResponse(BaseSerializerModel):
    link_id: int
    patient_id: int
    status: str
    linked_at: datetime


# 연동 목록 조회 - REQ-USER-006
class LinkListItemResponse(BaseSerializerModel):
    link_id: int
    patient_id: int
    patient_user_id: int | None
    patient_name: str | None
    caregiver_user_id: int
    caregiver_name: str | None
    status: str
    linked_at: datetime
    revoked_at: datetime | None


class LinkListResponse(BaseSerializerModel):
    role: str
    links: list[LinkListItemResponse]


class UnlinkResponse(BaseSerializerModel):
    link_id: int
    status: str
    revoked_at: datetime
