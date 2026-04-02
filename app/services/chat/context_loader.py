from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.models.chat import ChatSessionMemory
from app.models.dur import DurAlert
from app.models.guides import Guide, GuideStatus
from app.models.hospital_schedules import HospitalSchedule
from app.models.medications import PatientMed
from app.models.patients import PatientProfile
from app.models.schedules import IntakeLog, MedSchedule, MedScheduleTime
from app.services.chat.text_utils import dedupe_lines
from app.services.kids_client import KIDSClient


async def get_latest_done_guide(patient_id: int) -> Guide | None:
    return await Guide.filter(patient_id=patient_id, status=GuideStatus.DONE).order_by("-created_at", "-id").first()


async def get_active_meds(patient_id: int) -> list[dict[str, Any]]:
    rows = (
        await PatientMed.filter(
            patient_id=patient_id,
            is_active=True,
            confirmed_at__not_isnull=True,
        )
        .prefetch_related("drug_info_cache", "drug_catalog")
        .order_by("id")
        .all()
    )
    if not rows:
        rows = (
            await PatientMed.filter(
                patient_id=patient_id,
                is_active=True,
            )
            .prefetch_related("drug_info_cache", "drug_catalog")
            .order_by("id")
            .all()
        )

    results: list[dict[str, Any]] = []
    for row in rows:
        cache = getattr(row, "drug_info_cache", None)
        catalog = getattr(row, "drug_catalog", None)
        results.append(
            {
                "patient_med_id": int(row.id),
                "display_name": row.display_name,
                "dosage": row.dosage,
                "route": row.route,
                "notes": row.notes,
                "source_document_id": getattr(row, "source_document_id", None),
                "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
                "drug_info": {
                    "drug_name_display": getattr(cache, "drug_name_display", None),
                    "manufacturer": getattr(cache, "manufacturer", None),
                    "efficacy": getattr(cache, "efficacy", None),
                    "dosage_info": getattr(cache, "dosage_info", None),
                    "precautions": getattr(cache, "precautions", None),
                    "interactions": getattr(cache, "interactions", None),
                    "side_effects": getattr(cache, "side_effects", None),
                    "storage_method": getattr(cache, "storage_method", None),
                },
                "drug_catalog": {
                    "name": getattr(catalog, "name", None),
                    "ingredients": getattr(catalog, "ingredients", None),
                    "warnings": getattr(catalog, "warnings", None),
                    "manufacturer": getattr(catalog, "manufacturer", None),
                },
            }
        )
    return results


async def get_active_schedules(patient_id: int) -> list[dict[str, Any]]:
    schedules = await MedSchedule.filter(
        patient_id=patient_id,
        status="active",
    ).all()

    if not schedules:
        return []

    schedule_ids = [int(s.id) for s in schedules]
    schedule_times = await MedScheduleTime.filter(
        schedule_id__in=schedule_ids,
        is_active=True,
    ).all()

    time_map: dict[int, list[dict[str, Any]]] = {}
    for item in schedule_times:
        schedule_id = int(item.schedule_id)
        time_map.setdefault(schedule_id, []).append(
            {
                "time_of_day": str(item.time_of_day) if item.time_of_day else None,
                "days_of_week": item.days_of_week,
            }
        )

    results: list[dict[str, Any]] = []
    for schedule in schedules:
        results.append(
            {
                "schedule_id": int(schedule.id),
                "patient_med_id": int(schedule.patient_med_id),
                "times": time_map.get(int(schedule.id), []),
            }
        )

    return results


async def get_profile(patient_id: int) -> PatientProfile | None:
    return await PatientProfile.get_or_none(patient_id=patient_id, is_deleted=False)


async def get_hospital_schedules(patient_id: int) -> list[HospitalSchedule]:
    return await HospitalSchedule.filter(patient_id=patient_id).order_by("scheduled_at", "id").all()


async def get_active_dur_alerts(patient_id: int) -> list[dict[str, Any]]:
    rows = (
        await DurAlert.filter(patient_id=patient_id, is_active=True)
        .prefetch_related("patient_med", "related_patient_med")
        .order_by("-created_at", "-id")
        .all()
    )

    results: list[dict[str, Any]] = []
    for row in rows:
        patient_med = getattr(row, "patient_med", None)
        related_med = getattr(row, "related_patient_med", None)
        results.append(
            {
                "alert_type": str(getattr(row, "alert_type", "") or "").strip(),
                "level": str(getattr(row, "level", "") or "").strip(),
                "message": str(getattr(row, "message", "") or "").strip(),
                "basis_json": str(getattr(row, "basis_json", "") or "").strip(),
                "patient_med_name": str(getattr(patient_med, "display_name", "") or "").strip(),
                "related_patient_med_name": str(getattr(related_med, "display_name", "") or "").strip(),
            }
        )
    return results


async def get_recent_adherence_summary(
    *,
    patient_id: int,
    meds: list[dict[str, Any]],
    format_datetime: Callable[[Any], str],
) -> dict[str, Any]:
    med_name_map = {
        int(med.get("patient_med_id")): str(med.get("display_name") or "").strip()
        for med in meds
        if med.get("patient_med_id") is not None
    }
    rows = await IntakeLog.filter(patient_id=patient_id).order_by("-scheduled_at", "-id").limit(20).all()

    if not rows:
        return {
            "total": 0,
            "taken": 0,
            "missed": 0,
            "pending": 0,
            "skipped": 0,
            "recent_missed_names": [],
            "recent_lines": [],
        }

    counts = {"taken": 0, "missed": 0, "pending": 0, "skipped": 0}
    recent_missed_names: list[str] = []
    recent_lines: list[str] = []
    for row in rows:
        status = str(getattr(row, "status", "") or "").strip().lower()
        if status in counts:
            counts[status] += 1
        med_name = med_name_map.get(
            int(getattr(row, "patient_med_id", 0) or 0),
            f"약 #{getattr(row, 'patient_med_id', '')}",
        )
        scheduled_at = format_datetime(getattr(row, "scheduled_at", None))
        if status == "missed" and med_name:
            recent_missed_names.append(med_name)
        status_label = {
            "taken": "복용 완료",
            "missed": "놓침",
            "pending": "대기",
            "skipped": "건너뜀",
        }.get(status, status or "기록")
        recent_lines.append(f"{scheduled_at} {med_name} - {status_label}")

    return {
        "total": len(rows),
        "taken": counts["taken"],
        "missed": counts["missed"],
        "pending": counts["pending"],
        "skipped": counts["skipped"],
        "recent_missed_names": dedupe_lines(recent_missed_names, limit=4),
        "recent_lines": dedupe_lines(recent_lines, limit=4),
    }


async def get_session_memory(session_id: int) -> ChatSessionMemory | None:
    return await ChatSessionMemory.get_or_none(session_id=session_id)


async def build_kids_evidence(*, meds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client = KIDSClient()
    if not client.is_enabled():
        return []

    evidence: list[dict[str, Any]] = []
    for med in meds[:5]:
        drug_name = str(med.get("display_name") or "").strip()
        if not drug_name:
            continue
        items = await client.search_safety_evidence(drug_name)
        evidence.extend(items)

    return evidence[:10]

