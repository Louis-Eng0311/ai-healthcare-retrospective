from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# 가이드 생성 요청
class GuideGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(..., ge=1, description="가이드 생성 기준 문서 ID")


# 가이드 생성 응답 data
class GuideGenerateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_id: int = Field(ge=1)
    status: str = Field(min_length=1)


# 가이드 생성 응답
class GuideGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: GuideGenerateData


# 가이드 목록 아이템
class GuideListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_id: int = Field(ge=1)
    patient_id: int = Field(ge=1)
    document_id: int = Field(ge=1)
    version: int = Field(ge=1)
    status: str = Field(min_length=1)
    created_at: datetime


# 가이드 목록 응답 data
class GuideListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GuideListItem]
    total: int = Field(ge=0)


# 가이드 목록 응답
class GuideListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: GuideListData


# 가이드 상세 응답 data
class GuideDetailData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_id: int = Field(ge=1)
    patient_id: int = Field(ge=1)
    document_id: int = Field(ge=1)
    version: int = Field(ge=1)
    status: str = Field(min_length=1)

    content_text: str | None = None
    content_json: dict[str, Any] | None = None
    caregiver_summary: dict[str, Any] | None = None

    disclaimer: str = Field(min_length=1)

    created_at: datetime
    updated_at: datetime


# 가이드 상세 응답
class GuideDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: GuideDetailData


# 가이드 재생성 응답 data
class GuideRegenerateData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_id: int = Field(ge=1)
    status: str = Field(min_length=1)


# 가이드 재생성 응답
class GuideRegenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool = True
    data: GuideRegenerateData
