from __future__ import annotations

import json
from datetime import datetime

from app.core import config
from app.models.patients import PatientProfile, PatientProfileHistory


# ------------------------------------------------------------
# 건강 프로필 현재 상태를 snapshot dict 로 변환하는 함수
# ------------------------------------------------------------
def _profile_snapshot(profile: PatientProfile | None) -> dict | None:
    if profile is None:
        return None

    pid = getattr(profile, "patient_id", None) or profile.patient.id

    return {
        "patient_id": pid,
        "birth_year": profile.birth_year,
        "sex": profile.sex,
        "height_cm": str(profile.height_cm) if profile.height_cm is not None else None,
        "weight_kg": str(profile.weight_kg) if profile.weight_kg is not None else None,
        "bmi": str(profile.bmi) if profile.bmi is not None else None,
        "conditions": profile.conditions,
        "allergies": profile.allergies,
        "notes": profile.notes,
        "meds_json": profile.meds_json,
        "is_smoker": profile.is_smoker,
        "is_hospitalized": profile.is_hospitalized,
        "discharge_date": profile.discharge_date.isoformat() if profile.discharge_date else None,
        "avg_sleep_hours_per_day": (
            str(profile.avg_sleep_hours_per_day) if profile.avg_sleep_hours_per_day is not None else None
        ),
        "avg_cig_packs_per_week": (
            str(profile.avg_cig_packs_per_week) if profile.avg_cig_packs_per_week is not None else None
        ),
        "avg_alcohol_bottles_per_week": (
            str(profile.avg_alcohol_bottles_per_week) if profile.avg_alcohol_bottles_per_week is not None else None
        ),
        "avg_exercise_minutes_per_day": profile.avg_exercise_minutes_per_day,
        "is_deleted": getattr(profile, "is_deleted", False),
        "deleted_at": profile.deleted_at.isoformat() if getattr(profile, "deleted_at", None) else None,
        "deleted_by_user_id": getattr(profile, "deleted_by_user_id", None),
        "deleted_by_role": getattr(profile, "deleted_by_role", None),
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }


# ------------------------------------------------------------
# 건강 프로필 변경 이력을 저장하는 함수
# ------------------------------------------------------------
async def write_profile_history(
    *,
    patient_id: int,
    actor_user_id: int | None,
    actor_role: str | None,
    action: str,  # CREATE | UPDATE | DELETE
    profile: PatientProfile | None,
) -> None:
    now = datetime.now(config.TIMEZONE)

    payload = {
        "action": action,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "at": now.isoformat(),
        "profile": _profile_snapshot(profile),
    }

    await PatientProfileHistory.create(
        patient_id=patient_id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        snapshot_json=json.dumps(payload, ensure_ascii=False),
    )
