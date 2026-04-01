# 20260303 알림설정 HYJ app/dtos/notifications.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# 공통 응답 Envelope (명세서 규약: success / data)
# =============================================================================
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """
    모든 API 응답을 { success, data } 형태로 통일하기 위한 Envelope.
    - 에러는 FastAPI 기본 HTTPException 처리에 맡기거나
      별도 error envelope 정책이 있다면 확장 가능
    """

    success: bool = True
    data: T


# =============================================================================
# Notifications - List Item / List Response
# =============================================================================
class NotificationItem(BaseModel):
    """
    알림센터 목록에 내려줄 단일 알림 DTO
    """

    id: int
    type: str
    title: str | None = None
    body: str | None = None

    # DB에는 payload_json(TEXT)이지만, API로는 dict로 통일
    payload: dict[str, Any] = Field(default_factory=dict)

    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """
    커서 기반 페이지네이션 응답
    """

    items: list[NotificationItem]
    next_cursor: int | None = None


# =============================================================================
# Notification Settings
# =============================================================================
class NotificationSettingsResponse(BaseModel):
    """
    settings 모델에서 그대로 validate 할 수 있게 구성
    - 너희 NotificationSettings 모델 필드명과 일치해야 함
    """

    model_config = ConfigDict(from_attributes=True)

    intake_reminder: bool = True
    missed_alert: bool = True
    hospital_schedule_reminder: bool = True
    ocr_done: bool = True
    guide_ready: bool = True


class NotificationSettingsUpdateRequest(BaseModel):
    """
    PATCH /notifications/settings
    - partial update 허용
    """

    intake_reminder: bool | None = None
    missed_alert: bool | None = None
    hospital_schedule_reminder: bool | None = None
    ocr_done: bool | None = None
    guide_ready: bool | None = None


# =============================================================================
# Manual Remind (POST /notifications/remind)
# =============================================================================
class NotificationRemindRequest(BaseModel):
    """
    보호자가 환자에게 수동 리마인드 발송

    최소 필수:
    - patient_id
    나머지는 optional로 둬서 프론트/기획 변경에 유연하게 대응
    """

    patient_id: int = Field(..., description="알림을 받을 patient id")

    # type: 알림센터 유형(예: intake_reminder, missed_alert ...)
    # 더미 SQL에서 notifications.type 은 'intake_reminder', 'missed_alert' 로 들어감 :contentReference[oaicite:0]{index=0}
    type: str = Field(default="intake_reminder")

    title: str | None = Field(default="복약 리마인드")
    message: str | None = Field(default="복약 시간이예요! 확인해 주세요.")

    # payload: 알림 상세 화면 이동/딥링크를 위한 추가 데이터
    # payload: Optional[Dict[str, Any]] = None
    payload: dict[str, Any] | None = Field(
        default=None,
        description="알림 상세 화면 이동/딥링크를 위한 추가 데이터",
        examples=[{"schedule_id": 50001, "deeplink": "/schedules/50001"}],
    )


class NotificationRemindData(BaseModel):
    """
    POST /notifications/remind 성공 시 data payload
    """

    notification_id: int
    patient_id: int
    sent_to_user_id: int
    type: str
    created_at: datetime
