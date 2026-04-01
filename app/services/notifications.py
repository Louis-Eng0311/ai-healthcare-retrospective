# 20260303 알림설정 HYJ app/services/notifications.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

# notification_settings 테이블용 모델
from app.models.notification_settings import NotificationSettings

# -----------------------------------------------------------------------------
# Model imports
# -----------------------------------------------------------------------------
# notifications 테이블용 모델
from app.models.notifications import Notification

# patients 테이블용 모델
from app.models.patients import Patient
from app.services.queue_service import enqueue_send_notification


# -----------------------------------------------------------------------------
# 시간 유틸
# -----------------------------------------------------------------------------
def now_utc_naive() -> datetime:
    """
    프로젝트 DB가 naive datetime(타임존 없는 datetime)을 쓰는 경우가 많아서
    UTC 기반 naive datetime으로 통일해 저장한다.

    - timezone-aware datetime을 넣으면 ORM/DB 설정에 따라 경고/오류가 날 수 있음
    - 기존 코드에서도 naive로 맞추고 있어서 그 정책을 유지
    """
    return datetime.now(UTC).replace(tzinfo=None)


# -----------------------------------------------------------------------------
# CaregiverPatientLink 모델 위치가 프로젝트에서 헷갈리는 문제를 흡수하기 위한 helper
# -----------------------------------------------------------------------------
def _resolve_caregiver_patient_link_model() -> type:
    """
    너 프로젝트는 caregiver_patient_links 테이블 모델이
    - app.models.caregiver_patient_links.py 에 있기도 하고
    - app.models.patients.py 안에 같이 들어있기도 해서
    import가 자주 깨진다.

    서비스는 아래 우선순위로 모델을 찾아서 사용한다:
    1) app.models.caregiver_patient_links.CaregiverPatientLink
    2) app.models.patients.CaregiverPatientLink

    둘 다 없으면 명확하게 500으로 터뜨려서 팀원이 바로 고칠 수 있게 한다.
    """
    try:
        from app.models.caregiver_patient_links import CaregiverPatientLink  # type: ignore

        return CaregiverPatientLink
    except Exception:
        pass

    try:
        from app.models.patients import CaregiverPatientLink  # type: ignore

        return CaregiverPatientLink
    except Exception as e:
        raise RuntimeError(
            "CaregiverPatientLink model not found. "
            "Expected in app.models.caregiver_patient_links or app.models.patients"
        ) from e


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------
class NotificationService:
    """
    Notifications 도메인 서비스.

    구현 철학:
    - Router는 “요청/응답 스키마와 인증 주입”만 담당
    - Service는 “권한/검증/DB 트랜잭션/도메인 로직”을 담당
    """

    # -------------------------------------------------------------------------
    # 1) 알림 목록 (커서 기반)
    # -------------------------------------------------------------------------
    async def list_notifications(
        self,
        user_id: int,
        cursor: int | None = None,
        limit: int = 20,
        unread_only: bool = False,
        patient_id: int | None = None,
    ) -> tuple[list[Notification], int | None]:
        """
        GET /notifications
        - 최신순(id desc)
        - cursor가 있으면 id < cursor 로 다음 페이지
        - unread_only면 read_at IS NULL 조건
        """
        limit = max(1, min(limit, 100))

        qs = Notification.filter(user_id=user_id)

        if patient_id is not None:
            await self._ensure_user_can_access_patient(user_id=user_id, patient_id=patient_id)
            qs = qs.filter(patient_id=patient_id)

        if unread_only:
            qs = qs.filter(read_at__isnull=True)

        if cursor is not None:
            qs = qs.filter(id__lt=cursor)

        # limit+1로 하나 더 가져와서 next_cursor 계산
        rows = await qs.order_by("-id").limit(limit + 1)

        next_cursor: int | None = None
        if len(rows) > limit:
            # 현재 페이지 마지막 항목 id를 next cursor로 사용(id__lt 방식)
            next_cursor = rows[limit - 1].id
            rows = rows[:limit]

        return rows, next_cursor

    # -------------------------------------------------------------------------
    # 2) 단건 읽음 처리
    # -------------------------------------------------------------------------
    async def mark_read(self, user_id: int, notification_id: int) -> bool:
        """
        PATCH /notifications/{notification_id}/read
        - 내 알림만 읽음 처리 가능
        - 이미 읽은 건 idempotent하게 true
        """
        notif = await Notification.get_or_none(id=notification_id, user_id=user_id)
        if notif is None:
            return False

        if notif.read_at is None:
            notif.read_at = now_utc_naive()
            await notif.save(update_fields=["read_at"])

        return True

    # -------------------------------------------------------------------------
    # 3) 전체 읽음 처리
    # -------------------------------------------------------------------------
    async def mark_all_read(self, user_id: int, patient_id: int | None = None) -> int:
        """
        PATCH /notifications/read-all
        - 내 알림 중 unread(read_at is null)만 한번에 update
        - 반환값은 업데이트된 row count
        """
        qs = Notification.filter(user_id=user_id, read_at__isnull=True)
        if patient_id is not None:
            await self._ensure_user_can_access_patient(user_id=user_id, patient_id=patient_id)
            qs = qs.filter(patient_id=patient_id)
        return await qs.update(read_at=now_utc_naive())

    # -------------------------------------------------------------------------
    # 4) 미읽음 개수
    # -------------------------------------------------------------------------
    async def unread_count(self, user_id: int, patient_id: int | None = None) -> int:
        """
        GET /notifications/unread-count
        """
        qs = Notification.filter(user_id=user_id, read_at__isnull=True)
        if patient_id is not None:
            await self._ensure_user_can_access_patient(user_id=user_id, patient_id=patient_id)
            qs = qs.filter(patient_id=patient_id)
        return await qs.count()

    # -------------------------------------------------------------------------
    # 5) 알림 삭제
    # -------------------------------------------------------------------------
    async def delete_notification(self, user_id: int, notification_id: int) -> bool:
        """
        DELETE /notifications/{notification_id}
        - 내 알림만 삭제 가능
        """
        deleted = await Notification.filter(id=notification_id, user_id=user_id).delete()
        return deleted > 0

    # -------------------------------------------------------------------------
    # 6) 설정 조회/수정
    # -------------------------------------------------------------------------
    async def get_settings(self, user_id: int) -> NotificationSettings:
        """
        GET /notifications/settings
        - 없으면 기본값으로 생성
        """
        settings, _ = await NotificationSettings.get_or_create(user_id=user_id)
        return settings

    async def update_settings(self, user_id: int, data: Any) -> NotificationSettings:
        """
        PATCH /notifications/settings
        - partial update
        - data는 pydantic DTO(필드들이 Optional[bool])를 기대
        """
        settings, _ = await NotificationSettings.get_or_create(user_id=user_id)

        updated_fields: list[str] = []
        for field in (
            "intake_reminder",
            "missed_alert",
            "hospital_schedule_reminder",
            "ocr_done",
            "guide_ready",
        ):
            value = getattr(data, field, None)
            if value is not None:
                setattr(settings, field, value)
                updated_fields.append(field)

        if updated_fields:
            # updated_at은 모델에서 auto_now=True라 보통 자동 반영되는데,
            # update_fields로 지정하면 ORM 정책에 따라 누락될 수 있어 같이 넣어줌.
            await settings.save(update_fields=updated_fields + ["updated_at"])

        return settings

    # -------------------------------------------------------------------------
    # 7) 수동 리마인드(보호자 -> 환자)
    # -------------------------------------------------------------------------
    async def send_manual_remind(
        self,
        *,
        caregiver_user_id: int,
        patient_id: int,
        type: str,
        title: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        """
        POST /notifications/remind

        핵심 로직(너가 스웨거에 써둔 설명 그대로):
        1) caregiver가 patient에 접근 가능한지 검사
           - caregiver_patient_links(active & revoked_at is null) 또는
           - patients.owner_user_id(=보호자 owner)로 검사
        2) 환자의 수신자(user_id)를 결정: patients.user_id
        3) notifications.user_id = 환자 user_id 로 저장
        4) payload는 notifications.payload_json(TEXT)에 json string으로 저장

        NOTE:
        - 여기서 "CARE_GIVER role" 같은 RBAC는 프로젝트 전역 정책이 있으면
          router/dependency에서 강제하거나 이 서비스 앞단에서 추가하면 됨.
        """
        # --- 1) caregiver -> patient 접근 권한 체크 + 수신자 결정
        patient = await self._ensure_caregiver_can_access_patient(
            caregiver_user_id=caregiver_user_id,
            patient_id=patient_id,
        )
        recipient_user_id = patient.user_id  # 알림 받을 실제 유저

        # --- 2) payload 정리(무조건 dict -> json string)
        payload_dict = payload or {}
        payload_json = json.dumps(payload_dict, ensure_ascii=False)

        # --- 3) 트랜잭션으로 저장(추후 확장: 푸시 발송/이벤트 로그 등)
        async with in_transaction():
            notif = await Notification.create(
                user_id=recipient_user_id,
                patient_id=patient_id,
                type=type,
                title=title,
                body=message,
                payload_json=payload_json,
                sent_at=None,
                # Notification 생성 시: sent_at = NULL (아직 발송 안 됨)
                # worker가 job 처리 성공 시: sent_at = now()로 업데이트
                # read 처리 시: read_at 업데이트
                # read_at은 기본 None 유지
            )
        print("[enqueue] pushing notification job:", notif.id)
        await enqueue_send_notification(notif.id)

        return notif

    async def _ensure_caregiver_can_access_patient(
        self,
        *,
        caregiver_user_id: int,
        patient_id: int,
    ) -> Patient:
        """
        caregiver가 patient에 접근 가능한지 체크하고,
        가능하면 Patient를 반환한다.

        허용 조건(둘 중 하나라도 만족하면 OK):
        A) caregiver_patient_links 테이블에 (caregiver_user_id, patient_id) 활성 링크가 있다.
           - status='active' AND revoked_at IS NULL
        B) patients.owner_user_id == caregiver_user_id (보호자 owner)

        실패하면 403을 던진다.
        """
        patient = await Patient.get_or_none(id=patient_id)
        if patient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Patient not found.",
            )

        # B) owner 기반 체크(너 DB에서 owner_user_id가 보호자 의미로 쓰이고 있음)
        if getattr(patient, "owner_user_id", None) == caregiver_user_id:
            return patient

        # A) caregiver_patient_links 기반 체크(모델 위치가 프로젝트마다 달라서 resolve)
        caregiver_patient_link_model = _resolve_caregiver_patient_link_model()

        link = await caregiver_patient_link_model.get_or_none(
            caregiver_user_id=caregiver_user_id,
            patient_id=patient_id,
            status="active",
            revoked_at=None,
        )

        if link is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Caregiver cannot access this patient.",
            )

        return patient

    async def _ensure_user_can_access_patient(self, *, user_id: int, patient_id: int) -> Patient:
        patient = await Patient.get_or_none(id=patient_id)
        if patient is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found.")

        if getattr(patient, "user_id", None) == user_id or getattr(patient, "owner_user_id", None) == user_id:
            return patient

        caregiver_patient_link_model = _resolve_caregiver_patient_link_model()
        link = await caregiver_patient_link_model.get_or_none(
            caregiver_user_id=user_id,
            patient_id=patient_id,
            status="active",
            revoked_at=None,
        )
        if link is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
        return patient
