# 20260303 알림설정 HYJ app/apis/v1/notification_routers.py
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import ORJSONResponse as Response

from app.dependencies.security import get_request_user

# -----------------------------------------------------------------------------
# DTO import
# -----------------------------------------------------------------------------
# ✅ 아래 DTO들은 "명세서 응답 규약(success/data)"을 위해 사용한다.
# 네 프로젝트의 app/dtos/notifications.py에 아래 클래스들이 있어야 한다:
# - ApiResponse[T]  (success/data envelope)
# - NotificationItem
# - NotificationListResponse
# - NotificationSettingsResponse
# - NotificationSettingsUpdateRequest
# - NotificationRemindRequest
# - NotificationRemindData
#
# 만약 네 기존 DTO 이름이 다르면:
# - import 라인만 너희 이름에 맞게 바꿔주면 라우터는 그대로 동작함.
from app.dtos.notifications import (
    ApiResponse,
    NotificationItem,
    NotificationListResponse,
    NotificationRemindData,
    NotificationRemindRequest,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
)
from app.models.users import User
from app.services.notifications import NotificationService

notification_router = APIRouter(prefix="/notifications", tags=["notifications"])


# -----------------------------------------------------------------------------
# payload_json 정규화 유틸
# - DB 컬럼이 TEXT(JSON 문자열)인 경우가 많아서,
#   프론트로 내려줄 때는 항상 dict로 맞춰주는 게 안전하다.
# -----------------------------------------------------------------------------
def normalize_payload(payload: Any) -> dict:
    if payload is None:
        return {}

    if isinstance(payload, dict):
        return payload

    if isinstance(payload, str):
        payload = payload.strip()
        if not payload:
            return {}

        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                return parsed
            # dict가 아닌 JSON이면 value로 감싼다(프론트 타입 안정)
            return {"value": parsed}
        except Exception:
            return {"raw": payload}

    return {"raw": str(payload)}


# =============================================================================
# GET /notifications
# - 알림 목록 조회 (cursor pagination)
# - cursor: "이 id보다 작은 것" 다음 페이지
# - limit: 1~100
# - unread_only: 안 읽은 것만
#
# ✅ 명세서 규약 적용: {"success": true, "data": {...}}
# =============================================================================
@notification_router.get("", response_model=ApiResponse[NotificationListResponse])
async def list_notifications(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
    cursor: int | None = Query(default=None, description="cursor pagination id (id < cursor)"),
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    patient_id: int | None = Query(default=None),
) -> Response:
    rows, next_cursor = await service.list_notifications(
        user_id=user.id,
        cursor=cursor,
        limit=limit,
        unread_only=unread_only,
        patient_id=patient_id,
    )

    items = [
        NotificationItem(
            id=r.id,
            type=r.type,
            title=r.title,
            body=r.body,
            payload=normalize_payload(r.payload_json),
            read_at=r.read_at,
            created_at=r.created_at,
        )
        for r in rows
    ]

    data = NotificationListResponse(items=items, next_cursor=next_cursor)
    return Response(ApiResponse(data=data).model_dump())


# =============================================================================
# PATCH /notifications/{notification_id}/read
# - 알림 단건 읽음 처리
# =============================================================================
@notification_router.patch("/{notification_id}/read", response_model=ApiResponse[dict])
async def mark_notification_read(
    notification_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
) -> Response:
    ok = await service.mark_read(user_id=user.id, notification_id=notification_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    return Response(ApiResponse(data={"notification_id": notification_id, "read": True}).model_dump())


# =============================================================================
# DELETE /notifications/{notification_id}
# - 알림 단건 삭제
# =============================================================================
@notification_router.delete("/{notification_id}", response_model=ApiResponse[dict])
async def delete_notification(
    notification_id: int,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
) -> Response:
    ok = await service.delete_notification(user_id=user.id, notification_id=notification_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    return Response(ApiResponse(data={"notification_id": notification_id, "deleted": True}).model_dump())


# =============================================================================
# PATCH /notifications/read-all
# - 알림 전체 읽음 처리
# =============================================================================
@notification_router.patch("/read-all", response_model=ApiResponse[dict])
async def mark_all_notifications_read(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
    patient_id: int | None = Query(default=None),
) -> Response:
    updated = await service.mark_all_read(user_id=user.id, patient_id=patient_id)
    return Response(ApiResponse(data={"updated": updated}).model_dump())


# =============================================================================
# GET /notifications/unread-count
# - 읽지 않은 알림 개수
# =============================================================================
@notification_router.get("/unread-count", response_model=ApiResponse[dict])
async def unread_count(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
    patient_id: int | None = Query(default=None),
) -> Response:
    count = await service.unread_count(user_id=user.id, patient_id=patient_id)
    return Response(ApiResponse(data={"count": count}).model_dump())


# =============================================================================
# GET /notifications/settings
# - 알림 설정 조회
# =============================================================================
@notification_router.get("/settings", response_model=ApiResponse[NotificationSettingsResponse])
async def get_notification_settings(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
) -> Response:
    s = await service.get_settings(user_id=user.id)

    # Tortoise 모델 -> Pydantic DTO
    data = NotificationSettingsResponse.model_validate(s)
    return Response(ApiResponse(data=data).model_dump())


# =============================================================================
# PATCH /notifications/settings
# - 알림 설정 수정
# =============================================================================
@notification_router.patch("/settings", response_model=ApiResponse[NotificationSettingsResponse])
async def update_notification_settings(
    payload: NotificationSettingsUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
) -> Response:
    s = await service.update_settings(user_id=user.id, data=payload)
    data = NotificationSettingsResponse.model_validate(s)
    return Response(ApiResponse(data=data).model_dump())


# =============================================================================
# POST /notifications/remind
# - ✅ 명세서에 있는 기능: 보호자가 환자에게 수동 리마인드 보내기
# - 권한 검증/수신자 결정/알림 생성은 모두 service에서 처리
#
# 응답:
# - success/data 규약으로 반환
# =============================================================================
@notification_router.post(
    "/remind",
    response_model=ApiResponse[NotificationRemindData],
    status_code=status.HTTP_201_CREATED,
)
async def send_manual_remind(
    body: NotificationRemindRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotificationService, Depends(NotificationService)],
) -> Response:
    """
    보호자가 환자에게 수동 리마인드 발송

    service.send_manual_remind() 내부에서 처리:
    - caregiver_patient_links / patients.owner_user_id 기반 권한 체크
    - patients.user_id 기반 수신자(user_id) 결정
    - notifications.user_id = 수신자 user_id 로 저장
    """
    notif = await service.send_manual_remind(
        caregiver_user_id=user.id,
        patient_id=body.patient_id,
        type=body.type,
        title=body.title,
        message=body.message,
        payload=body.payload,
    )

    data = NotificationRemindData(
        notification_id=notif.id,
        patient_id=body.patient_id,
        sent_to_user_id=notif.user_id,
        type=notif.type,
        created_at=notif.created_at,
    )

    return Response(ApiResponse(data=data).model_dump())
