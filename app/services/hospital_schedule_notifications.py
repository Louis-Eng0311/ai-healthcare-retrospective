from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.hospital_schedules import HospitalSchedule
from app.models.notification_settings import NotificationSettings
from app.models.notifications import Notification
from app.services.queue_service import enqueue_send_notification

KST = ZoneInfo("Asia/Seoul")
HOSPITAL_SCHEDULE_NOTIFICATION_TYPE = "hospital_schedule_reminder"


def now_kst_naive() -> datetime:
    return datetime.now(KST).replace(tzinfo=None)


def build_hospital_schedule_due_times(scheduled_at: datetime) -> dict[str, datetime]:
    schedule_date = scheduled_at.date()
    day_before_at = datetime.combine(schedule_date - timedelta(days=1), time(hour=9, minute=0))

    if scheduled_at.time() < time(hour=9, minute=0):
        same_day_at = scheduled_at - timedelta(hours=2)
    else:
        same_day_at = datetime.combine(schedule_date, time(hour=9, minute=0))

    return {
        "day_before": day_before_at,
        "same_day": same_day_at,
    }


def build_hospital_schedule_message(schedule: HospitalSchedule, stage: str) -> tuple[str, str]:
    hospital_name = schedule.hospital_name or "병원"
    scheduled_label = schedule.scheduled_at.strftime("%Y-%m-%d %H:%M")

    if stage == "day_before":
        title = "내일 병원 일정이 있어요"
    else:
        title = "오늘 병원 일정이 있어요"

    body = f"{schedule.title} / {hospital_name} / {scheduled_label}"
    return title, body


async def _is_hospital_schedule_notification_enabled(user_id: int) -> bool:
    settings = await NotificationSettings.get_or_none(user_id=user_id)
    if settings is None:
        return True
    return bool(settings.hospital_schedule_reminder)


async def _notification_already_created(user_id: int, reminder_key: str) -> bool:
    return await Notification.filter(
        user_id=user_id,
        type=HOSPITAL_SCHEDULE_NOTIFICATION_TYPE,
        payload_json__contains=f'"reminder_key":"{reminder_key}"',
    ).exists()


async def dispatch_due_hospital_schedule_notifications(  # noqa: C901
    *,
    window_start: datetime,
    window_end: datetime,
) -> int:
    schedules = await HospitalSchedule.filter(
        scheduled_at__gte=window_start - timedelta(days=1),
        scheduled_at__lte=window_end + timedelta(days=2),
    ).prefetch_related("patient__user", "patient__caregiver_links__caregiver_user")

    created_count = 0

    for schedule in schedules:
        due_times = build_hospital_schedule_due_times(schedule.scheduled_at)
        recipients: set[int] = set()

        patient_user_id = getattr(schedule.patient, "user_id", None)
        if patient_user_id:
            recipients.add(int(patient_user_id))

        for link in getattr(schedule.patient, "caregiver_links", []):
            if getattr(link, "status", None) != "active" or getattr(link, "revoked_at", None) is not None:
                continue
            caregiver_user_id = getattr(link, "caregiver_user_id", None)
            if caregiver_user_id:
                recipients.add(int(caregiver_user_id))

        if not recipients:
            continue

        for stage, due_at in due_times.items():
            if due_at < window_start or due_at >= window_end:
                continue

            reminder_key = f"hospital:{schedule.id}:{stage}"
            title, body = build_hospital_schedule_message(schedule, stage)

            payload = {
                "patient_id": schedule.patient_id,
                "schedule_id": schedule.id,
                "scheduled_at": schedule.scheduled_at.isoformat(),
                "title": schedule.title,
                "hospital_name": schedule.hospital_name,
                "location": schedule.location,
                "reminder_stage": stage,
                "reminder_key": reminder_key,
            }
            payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

            for user_id in recipients:
                if not await _is_hospital_schedule_notification_enabled(user_id):
                    continue

                if await _notification_already_created(user_id, reminder_key):
                    continue

                notif = await Notification.create(
                    user_id=user_id,
                    patient_id=schedule.patient_id,
                    type=HOSPITAL_SCHEDULE_NOTIFICATION_TYPE,
                    title=title,
                    body=body,
                    payload_json=payload_json,
                    sent_at=None,
                )
                await enqueue_send_notification(notif.id)
                created_count += 1

    return created_count
