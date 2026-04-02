from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from tortoise.expressions import Q

from app.models.notification_settings import NotificationSettings
from app.models.notifications import Notification
from app.models.schedules import IntakeLog, MedSchedule, MedScheduleTime
from app.services.medication_intake_service import (
    GRACE_MINUTES,
    _normalize_time_of_day,
    _parse_days_of_week,
)
from app.services.queue_service import enqueue_send_notification

INTAKE_REMINDER_TYPE = "intake_reminder"
MISSED_ALERT_TYPE = "missed_alert"

MEAL_LABELS = (
    ("아침", 10),
    ("점심", 15),
    ("저녁", 20),
)


@dataclass(slots=True)
class MedicationSlot:
    patient_id: int
    patient_user_id: int | None
    patient_name: str | None
    schedule_id: int
    schedule_time_id: int
    patient_med_id: int
    medication_name: str | None
    scheduled_at: datetime
    caregiver_user_ids: list[int]


@dataclass(slots=True)
class MedicationGroup:
    patient_id: int
    patient_user_id: int | None
    patient_name: str | None
    caregiver_user_ids: list[int]
    scheduled_date: str
    meal_label: str
    stage: str
    slots: list[MedicationSlot]


def _daterange(date_from: date, date_to: date) -> list[date]:
    days: list[date] = []
    current = date_from
    while current <= date_to:
        days.append(current)
        current += timedelta(days=1)
    return days


def _infer_meal_label(scheduled_at: datetime) -> str:
    hour = scheduled_at.hour
    for label, hour_limit in MEAL_LABELS:
        if hour < hour_limit:
            return label
    return "취침 전"


def _build_reminder_key(group: MedicationGroup) -> str:
    return f"med:{group.patient_id}:{group.scheduled_date}:{group.meal_label}:{group.stage}"


def _build_group_payload(group: MedicationGroup) -> dict[str, object]:
    medication_names = [slot.medication_name for slot in group.slots if slot.medication_name]
    schedule_ids = sorted({slot.schedule_id for slot in group.slots})
    schedule_time_ids = sorted({slot.schedule_time_id for slot in group.slots})
    patient_med_ids = sorted({slot.patient_med_id for slot in group.slots})
    scheduled_times = [slot.scheduled_at.strftime("%H:%M") for slot in group.slots]

    return {
        "patient_id": group.patient_id,
        "patient_name": group.patient_name,
        "meal_label": group.meal_label,
        "scheduled_date": group.scheduled_date,
        "schedule_ids": schedule_ids,
        "schedule_time_ids": schedule_time_ids,
        "patient_med_ids": patient_med_ids,
        "medication_names": medication_names,
        "scheduled_times": scheduled_times,
        "type_stage": group.stage,
        "reminder_key": _build_reminder_key(group),
    }


def _join_medication_names(group: MedicationGroup) -> str:
    names = [slot.medication_name for slot in group.slots if slot.medication_name]
    if not names:
        return "등록된 약"
    return ", ".join(dict.fromkeys(names))


def _build_intake_message(group: MedicationGroup) -> tuple[str, str]:
    medication_names = _join_medication_names(group)
    return (
        f"{group.meal_label} 복약 시간이에요",
        f"{medication_names} 복용 여부를 확인해 주세요.",
    )


def _build_missed_message(group: MedicationGroup) -> tuple[str, str]:
    patient_name = group.patient_name or "환자"
    medication_names = _join_medication_names(group)
    return (
        f"{group.meal_label} 복약 확인이 필요해요",
        f"{patient_name}님의 {group.meal_label} 복약 기록이 아직 없어요. {medication_names} 복용 여부를 확인해 주세요.",
    )


def _extract_reminder_key(payload_json: str | None) -> str | None:
    if not payload_json:
        return None
    try:
        parsed: Any = json.loads(payload_json)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    reminder_key = parsed.get("reminder_key")
    if not isinstance(reminder_key, str):
        return None
    normalized = reminder_key.strip()
    return normalized or None


async def _load_settings_map(user_ids: set[int]) -> dict[int, NotificationSettings]:
    if not user_ids:
        return {}
    settings_rows = await NotificationSettings.filter(user_id__in=list(user_ids))
    return {int(row.user_id): row for row in settings_rows}


def _is_enabled_from_map(
    *, settings_map: dict[int, NotificationSettings], user_id: int, field_name: str
) -> bool:
    settings = settings_map.get(user_id)
    if settings is None:
        return True
    return bool(getattr(settings, field_name, True))


async def _load_existing_reminder_keys_map(
    *,
    user_ids: set[int],
    notification_type: str,
    date_from: date,
    date_to: date,
) -> dict[int, set[str]]:
    if not user_ids:
        return {}

    created_at_start = datetime.combine(date_from, time.min)
    created_at_end = datetime.combine(date_to + timedelta(days=1), time.min)
    rows = await Notification.filter(
        user_id__in=list(user_ids),
        type=notification_type,
        created_at__gte=created_at_start,
        created_at__lt=created_at_end,
        payload_json__contains='"reminder_key"',
    ).all()

    key_map: dict[int, set[str]] = {}
    for row in rows:
        reminder_key = _extract_reminder_key(getattr(row, "payload_json", None))
        if not reminder_key:
            continue
        key_map.setdefault(int(row.user_id), set()).add(reminder_key)
    return key_map


async def _load_candidate_slots(window_start: datetime, window_end: datetime) -> list[MedicationSlot]:  # noqa: C901
    grace = timedelta(minutes=GRACE_MINUTES)
    range_start = (window_start - grace).date()
    range_end = window_end.date()

    schedules = await MedSchedule.filter(
        Q(status="active"),
        Q(start_date__isnull=True) | Q(start_date__lte=range_end),
        Q(end_date__isnull=True) | Q(end_date__gte=range_start),
    ).prefetch_related("patient", "patient__caregiver_links", "patient_med")
    if not schedules:
        return []

    schedule_ids = [schedule.id for schedule in schedules]
    schedule_times = await MedScheduleTime.filter(schedule_id__in=schedule_ids, is_active=True).all()
    times_by_schedule: dict[int, list[MedScheduleTime]] = {}
    for schedule_time in schedule_times:
        times_by_schedule.setdefault(schedule_time.schedule_id, []).append(schedule_time)

    log_start = datetime.combine(range_start, time.min)
    log_end = datetime.combine(range_end + timedelta(days=1), time.min)
    logs = await IntakeLog.filter(scheduled_at__gte=log_start, scheduled_at__lt=log_end).all()
    log_map: dict[tuple[int, datetime], IntakeLog] = {}
    for log in logs:
        key = (log.schedule_time_id, log.scheduled_at.replace(microsecond=0))
        log_map[key] = log

    slots: list[MedicationSlot] = []
    for schedule in schedules:
        caregiver_user_ids = [
            int(link.caregiver_user_id)
            for link in getattr(schedule.patient, "caregiver_links", [])
            if getattr(link, "status", None) == "active" and getattr(link, "revoked_at", None) is None
        ]
        patient_name = getattr(schedule.patient, "display_name", None)
        medication_name = getattr(getattr(schedule, "patient_med", None), "display_name", None)

        for day in _daterange(range_start, range_end):
            if schedule.start_date and day < schedule.start_date:
                continue
            if schedule.end_date and day > schedule.end_date:
                continue

            for schedule_time in times_by_schedule.get(schedule.id, []):
                allowed_days = _parse_days_of_week(schedule_time.days_of_week)
                if allowed_days is not None and day.weekday() not in allowed_days:
                    continue

                slot_time = _normalize_time_of_day(schedule_time.time_of_day)
                scheduled_at = datetime.combine(day, slot_time).replace(microsecond=0)
                key = (schedule_time.id, scheduled_at)

                if key in log_map:
                    continue

                slots.append(
                    MedicationSlot(
                        patient_id=schedule.patient_id,
                        patient_user_id=getattr(schedule.patient, "user_id", None),
                        patient_name=patient_name,
                        schedule_id=schedule.id,
                        schedule_time_id=schedule_time.id,
                        patient_med_id=schedule.patient_med_id,
                        medication_name=medication_name,
                        scheduled_at=scheduled_at,
                        caregiver_user_ids=caregiver_user_ids,
                    )
                )

    return slots


def _group_slots(slots: list[MedicationSlot], stage: str) -> list[MedicationGroup]:
    grouped: dict[tuple[int, str, str], MedicationGroup] = {}

    for slot in sorted(slots, key=lambda current: (current.patient_id, current.scheduled_at, current.schedule_id)):
        meal_label = _infer_meal_label(slot.scheduled_at)
        scheduled_date = slot.scheduled_at.date().isoformat()
        key = (slot.patient_id, scheduled_date, meal_label)

        group = grouped.get(key)
        if group is None:
            group = MedicationGroup(
                patient_id=slot.patient_id,
                patient_user_id=slot.patient_user_id,
                patient_name=slot.patient_name,
                caregiver_user_ids=slot.caregiver_user_ids,
                scheduled_date=scheduled_date,
                meal_label=meal_label,
                stage=stage,
                slots=[],
            )
            grouped[key] = group

        group.slots.append(slot)

    return list(grouped.values())


async def dispatch_due_medication_notifications(*, window_start: datetime, window_end: datetime) -> int:
    grace = timedelta(minutes=GRACE_MINUTES)
    created_count = 0
    slots = await _load_candidate_slots(window_start, window_end)

    intake_groups = _group_slots(
        [slot for slot in slots if window_start <= slot.scheduled_at < window_end],
        "intake",
    )
    missed_groups = _group_slots(
        [slot for slot in slots if window_start <= (slot.scheduled_at + grace) < window_end],
        "missed",
    )

    intake_user_ids = {int(group.patient_user_id) for group in intake_groups if group.patient_user_id}
    missed_user_ids = {int(user_id) for group in missed_groups for user_id in group.caregiver_user_ids}
    all_group_dates = [
        datetime.fromisoformat(group.scheduled_date).date()
        for group in [*intake_groups, *missed_groups]
    ]
    date_from = min(all_group_dates) if all_group_dates else (window_start - grace).date()
    date_to = max(all_group_dates) if all_group_dates else window_end.date()

    intake_settings_map = await _load_settings_map(intake_user_ids)
    missed_settings_map = await _load_settings_map(missed_user_ids)
    intake_existing_keys = await _load_existing_reminder_keys_map(
        user_ids=intake_user_ids,
        notification_type=INTAKE_REMINDER_TYPE,
        date_from=date_from,
        date_to=date_to,
    )
    missed_existing_keys = await _load_existing_reminder_keys_map(
        user_ids=missed_user_ids,
        notification_type=MISSED_ALERT_TYPE,
        date_from=date_from,
        date_to=date_to,
    )

    for group in intake_groups:
        if not group.patient_user_id:
            continue

        patient_user_id = int(group.patient_user_id)
        reminder_key = _build_reminder_key(group)
        if not _is_enabled_from_map(
            settings_map=intake_settings_map,
            user_id=patient_user_id,
            field_name="intake_reminder",
        ):
            continue
        if reminder_key in intake_existing_keys.get(patient_user_id, set()):
            continue

        title, body = _build_intake_message(group)
        payload_json = json.dumps(_build_group_payload(group), ensure_ascii=False, separators=(",", ":"))
        notif = await Notification.create(
            user_id=patient_user_id,
            patient_id=group.patient_id,
            type=INTAKE_REMINDER_TYPE,
            title=title,
            body=body,
            payload_json=payload_json,
            sent_at=None,
        )
        await enqueue_send_notification(notif.id)
        intake_existing_keys.setdefault(patient_user_id, set()).add(reminder_key)
        created_count += 1

    for group in missed_groups:
        if not group.caregiver_user_ids:
            continue

        reminder_key = _build_reminder_key(group)
        title, body = _build_missed_message(group)
        payload_json = json.dumps(_build_group_payload(group), ensure_ascii=False, separators=(",", ":"))

        for caregiver_user_id in group.caregiver_user_ids:
            normalized_caregiver_user_id = int(caregiver_user_id)
            if not _is_enabled_from_map(
                settings_map=missed_settings_map,
                user_id=normalized_caregiver_user_id,
                field_name="missed_alert",
            ):
                continue
            if reminder_key in missed_existing_keys.get(normalized_caregiver_user_id, set()):
                continue

            notif = await Notification.create(
                user_id=normalized_caregiver_user_id,
                patient_id=group.patient_id,
                type=MISSED_ALERT_TYPE,
                title=title,
                body=body,
                payload_json=payload_json,
                sent_at=None,
            )
            await enqueue_send_notification(notif.id)
            missed_existing_keys.setdefault(normalized_caregiver_user_id, set()).add(reminder_key)
            created_count += 1

    return created_count
