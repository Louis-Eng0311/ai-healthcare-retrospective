from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from starlette import status

from app.core import config
from app.dtos.patient_profile import PatientProfileOut, PatientProfileUpsertIn
from app.models.patients import Patient, PatientProfile
from app.models.users import User
from app.services.patient_profile_access import (
    get_linked_patient_or_404,
    get_my_patient_or_404,
    resolve_actor_role,
)
from app.services.patient_profile_history_service import write_profile_history
from app.utils.jwt.health_profile import (
    calc_bmi,
    dumps_str_list,
    loads_str_list,
    normalize_sex,
    round_0,
    round_1,
)


# ------------------------------------------------------------
# Decimal / 기타 값을 float 로 안전하게 변환하는 함수
# ------------------------------------------------------------
def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


# ------------------------------------------------------------
# DB TEXT(JSON 문자열 / CSV / 줄바꿈 문자열)를 list[str]로 변환하는 함수
# ------------------------------------------------------------
def _to_list(v: str | None) -> list[str]:
    if not v:
        return []

    try:
        data = json.loads(v)
        if isinstance(data, list):
            return [str(x).strip() for x in data if x is not None and str(x).strip()]
    except Exception:
        pass

    parts = [p.strip() for chunk in str(v).splitlines() for p in chunk.split(",")]
    return [p for p in parts if p]


# ------------------------------------------------------------
# BMI 상태와 정중한 안내 문구를 반환하는 함수
# ------------------------------------------------------------
def get_bmi_status(bmi: float | None) -> tuple[str | None, str | None]:
    if bmi is None:
        return None, None

    if bmi < 18.5:
        return (
            "저체중",
            "현재 체중이 표준 범위보다 다소 낮은 편으로 확인됩니다. 균형 잡힌 식사와 건강 상태 점검을 권장드립니다.",
        )

    if bmi < 23:
        return (
            "정상",
            "현재 체중은 건강한 범위에 해당합니다. 지금의 생활습관을 유지하시는 것을 권장드립니다.",
        )

    if bmi < 25:
        return (
            "과체중",
            "현재 체중이 표준 범위를 약간 초과한 상태입니다. 식습관 관리와 규칙적인 신체 활동을 통해 건강 관리에 유의하시길 권장드립니다.",
        )

    return (
        "비만",
        "현재 체중이 권장 범위를 초과한 상태입니다. 건강 관리를 위해 식습관 조절과 규칙적인 운동을 고려해보시기를 권장드립니다.",
    )


# ------------------------------------------------------------
# 프로필 payload 를 DB 모델에 반영하는 공통 함수
# ------------------------------------------------------------
def _apply_payload(profile: PatientProfile, payload: PatientProfileUpsertIn) -> None:
    profile.birth_year = payload.birth_year
    profile.sex = normalize_sex(payload.sex)

    profile.height_cm = round_1(payload.height_cm)
    profile.weight_kg = round_1(payload.weight_kg)
    profile.bmi = calc_bmi(profile.height_cm, profile.weight_kg)

    profile.conditions = dumps_str_list(payload.conditions)
    profile.allergies = dumps_str_list(payload.allergies)
    profile.meds_json = dumps_str_list(payload.meds)

    profile.is_smoker = payload.is_smoker
    profile.is_hospitalized = payload.is_hospitalized
    profile.discharge_date = None if payload.is_hospitalized is False else payload.discharge_date
    profile.notes = payload.notes

    profile.avg_sleep_hours_per_day = round_1(payload.avg_sleep_hours_per_day)
    profile.avg_cig_packs_per_week = round_1(payload.avg_cig_packs_per_week)
    profile.avg_alcohol_bottles_per_week = round_1(payload.avg_alcohol_bottles_per_week)
    profile.avg_exercise_minutes_per_day = round_0(payload.avg_exercise_minutes_per_day)


# ------------------------------------------------------------
# soft delete 시 운영용 데이터를 비우는 함수
# ------------------------------------------------------------
def _clear_profile_for_soft_delete(profile: PatientProfile, *, actor_user_id: int, actor_role: str) -> None:
    profile.birth_year = None
    profile.sex = None

    profile.height_cm = None
    profile.weight_kg = None
    profile.bmi = None

    profile.conditions = None
    profile.allergies = None
    profile.notes = None
    profile.meds_json = None

    profile.is_smoker = None
    profile.is_hospitalized = None
    profile.discharge_date = None

    profile.avg_sleep_hours_per_day = None
    profile.avg_cig_packs_per_week = None
    profile.avg_alcohol_bottles_per_week = None
    profile.avg_exercise_minutes_per_day = None

    profile.is_deleted = True
    profile.deleted_at = datetime.now(config.TIMEZONE)
    profile.deleted_by_user_id = actor_user_id
    profile.deleted_by_role = actor_role


# ------------------------------------------------------------
# 활성 프로필만 조회하는 함수
# ------------------------------------------------------------
async def _get_active_profile_or_404(patient: Patient) -> PatientProfile:
    profile = await PatientProfile.get_or_none(patient_id=patient.id, is_deleted=False)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="건강 프로필을 찾을 수 없습니다.",
        )
    return profile


# ------------------------------------------------------------
# 활성/삭제 여부와 무관하게 프로필 row 를 조회하는 함수
# ------------------------------------------------------------
async def _get_any_profile(patient: Patient) -> PatientProfile | None:
    return await PatientProfile.get_or_none(patient_id=patient.id)


# ------------------------------------------------------------
# PatientProfile 모델을 API 응답 DTO 로 변환하는 함수
# ------------------------------------------------------------
def _to_out(profile: PatientProfile) -> PatientProfileOut:
    pid = getattr(profile, "patient_id", None) or profile.patient.id

    bmi_value = _to_float(round_1(profile.bmi)) if profile.bmi is not None else None
    bmi_status, bmi_comment = get_bmi_status(bmi_value)

    return PatientProfileOut(
        patient_id=pid,
        birth_year=profile.birth_year,
        sex=profile.sex,
        height_cm=_to_float(round_1(profile.height_cm)),
        weight_kg=_to_float(round_1(profile.weight_kg)),
        bmi=bmi_value,
        bmi_status=bmi_status,
        bmi_comment=bmi_comment,
        conditions=_to_list(profile.conditions),
        allergies=_to_list(profile.allergies),
        meds=loads_str_list(profile.meds_json),
        is_smoker=profile.is_smoker,
        is_hospitalized=profile.is_hospitalized,
        discharge_date=profile.discharge_date,
        notes=profile.notes,
        avg_sleep_hours_per_day=_to_float(round_1(profile.avg_sleep_hours_per_day)),
        avg_cig_packs_per_week=_to_float(round_1(profile.avg_cig_packs_per_week)),
        avg_alcohol_bottles_per_week=_to_float(round_1(profile.avg_alcohol_bottles_per_week)),
        avg_exercise_minutes_per_day=profile.avg_exercise_minutes_per_day,
    )


# ------------------------------------------------------------
# 프로필 생성 또는 soft delete 상태 복구를 수행하는 공통 함수
# ------------------------------------------------------------
async def _create_or_restore_profile(
    *,
    patient: Patient,
    actor_user_id: int,
    actor_role: str,
    payload: PatientProfileUpsertIn,
) -> PatientProfileOut:
    existing = await _get_any_profile(patient)

    if existing and not existing.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 등록된 건강 프로필이 있습니다.",
        )

    # 🔴 CHANGED: soft deleted row 가 있으면 복구 후 재사용
    if existing and existing.is_deleted:
        profile = existing
        profile.is_deleted = False
        profile.deleted_at = None
        profile.deleted_by_user_id = None
        profile.deleted_by_role = None
    else:
        profile = PatientProfile(patient=patient)

    _apply_payload(profile, payload)
    await profile.save()

    await write_profile_history(
        patient_id=patient.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action="CREATE",
        profile=profile,
    )

    return _to_out(profile)


# ------------------------------------------------------------
# 활성 프로필 수정 공통 함수
# ------------------------------------------------------------
async def _update_profile(
    *,
    patient: Patient,
    actor_user_id: int,
    actor_role: str,
    payload: PatientProfileUpsertIn,
) -> PatientProfileOut:
    profile = await _get_active_profile_or_404(patient)

    _apply_payload(profile, payload)
    await profile.save()

    await write_profile_history(
        patient_id=patient.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action="UPDATE",
        profile=profile,
    )

    return _to_out(profile)


# ------------------------------------------------------------
# 활성 프로필 soft delete 공통 함수
# ------------------------------------------------------------
async def _soft_delete_profile(
    *,
    patient: Patient,
    actor_user_id: int,
    actor_role: str,
) -> None:
    profile = await _get_active_profile_or_404(patient)

    # 삭제 직전 스냅샷 저장
    await write_profile_history(
        patient_id=patient.id,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action="DELETE",
        profile=profile,
    )

    _clear_profile_for_soft_delete(profile, actor_user_id=actor_user_id, actor_role=actor_role)
    await profile.save()


# ------------------------------------------------------------
# 환자 본인 건강 프로필 조회 함수
# ------------------------------------------------------------
async def get_my_patient_profile(user: User) -> PatientProfileOut:
    patient = await get_my_patient_or_404(user)
    profile = await _get_active_profile_or_404(patient)
    return _to_out(profile)


# ------------------------------------------------------------
# 환자 본인 건강 프로필 생성 함수
# ------------------------------------------------------------
async def create_my_patient_profile(user: User, payload: PatientProfileUpsertIn) -> PatientProfileOut:
    patient = await get_my_patient_or_404(user)
    actor_role = await resolve_actor_role(user)
    return await _create_or_restore_profile(
        patient=patient,
        actor_user_id=user.id,
        actor_role=actor_role,
        payload=payload,
    )


# ------------------------------------------------------------
# 환자 본인 건강 프로필 수정 함수
# ------------------------------------------------------------
async def update_my_patient_profile(user: User, payload: PatientProfileUpsertIn) -> PatientProfileOut:
    patient = await get_my_patient_or_404(user)
    actor_role = await resolve_actor_role(user)
    return await _update_profile(
        patient=patient,
        actor_user_id=user.id,
        actor_role=actor_role,
        payload=payload,
    )


# ------------------------------------------------------------
# 환자 본인 건강 프로필 삭제 함수 (soft delete)
# ------------------------------------------------------------
async def delete_my_patient_profile(user: User) -> None:
    patient = await get_my_patient_or_404(user)
    actor_role = await resolve_actor_role(user)
    await _soft_delete_profile(
        patient=patient,
        actor_user_id=user.id,
        actor_role=actor_role,
    )


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 조회 함수
# ------------------------------------------------------------
async def get_linked_patient_profile(caregiver: User, link_id: int) -> PatientProfileOut:
    patient = await get_linked_patient_or_404(caregiver, link_id)
    profile = await _get_active_profile_or_404(patient)
    return _to_out(profile)


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 생성 함수
# ------------------------------------------------------------
async def create_linked_patient_profile(
    caregiver: User,
    link_id: int,
    payload: PatientProfileUpsertIn,
) -> PatientProfileOut:
    patient = await get_linked_patient_or_404(caregiver, link_id)
    return await _create_or_restore_profile(
        patient=patient,
        actor_user_id=caregiver.id,
        actor_role="CAREGIVER",
        payload=payload,
    )


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 수정 함수
# ------------------------------------------------------------
async def update_linked_patient_profile(
    caregiver: User,
    link_id: int,
    payload: PatientProfileUpsertIn,
) -> PatientProfileOut:
    patient = await get_linked_patient_or_404(caregiver, link_id)
    return await _update_profile(
        patient=patient,
        actor_user_id=caregiver.id,
        actor_role="CAREGIVER",
        payload=payload,
    )


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 삭제 함수 (soft delete)
# ------------------------------------------------------------
async def delete_linked_patient_profile(caregiver: User, link_id: int) -> None:
    patient = await get_linked_patient_or_404(caregiver, link_id)
    await _soft_delete_profile(
        patient=patient,
        actor_user_id=caregiver.id,
        actor_role="CAREGIVER",
    )
