from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from app.models.guides import Guide, GuideStatus
from app.models.notification_settings import NotificationSettings
from app.models.notifications import Notification
from app.models.patients import CaregiverPatientLink, Patient, PatientProfile
from app.services.guide import GuideContextBundle, GuideService, GuideServiceError
from app.services.guide_validation import get_guide_disclaimer, validate_guide_payload
from app.services.queue_service import enqueue_send_notification

logger = logging.getLogger(__name__)

DISCLAIMER = get_guide_disclaimer()
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


# OpenAI API 키 조회
def _get_openai_key() -> str:
    key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    return key


# OpenAI 모델명 조회
def _get_openai_model() -> str:
    return (os.getenv("OPENAI_MODEL", "gpt-4o-mini") or "").strip()


# 프롬프트 파일 읽기
def _read_prompt_template(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise RuntimeError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


# 환자 대상자 톤 분류
def _audience_from_profile(profile: PatientProfile | None) -> str:
    birth_year = getattr(profile, "birth_year", None)
    if not birth_year:
        return "adult"

    age = date.today().year - int(birth_year)

    if age <= 12:
        return "child"
    if 13 <= age <= 17:
        return "teen"
    if age >= 65:
        return "senior"
    return "adult"


# 건강 프로필 텍스트 구성
def _build_profile_text(profile: PatientProfile | None) -> str:
    if not profile:
        return "등록된 건강 프로필 없음"

    lines: list[str] = []

    if getattr(profile, "birth_year", None):
        lines.append(f"- 출생연도: {profile.birth_year}")
    if getattr(profile, "sex", None):
        lines.append(f"- 성별: {profile.sex}")
    if getattr(profile, "height_cm", None):
        lines.append(f"- 키(cm): {profile.height_cm}")
    if getattr(profile, "weight_kg", None):
        lines.append(f"- 체중(kg): {profile.weight_kg}")
    if getattr(profile, "bmi", None):
        lines.append(f"- BMI: {profile.bmi}")
    if getattr(profile, "conditions", None):
        lines.append(f"- 기저질환/상태: {profile.conditions}")
    if getattr(profile, "allergies", None):
        lines.append(f"- 알레르기: {profile.allergies}")
    if getattr(profile, "notes", None):
        lines.append(f"- 메모: {profile.notes}")
    if getattr(profile, "is_smoker", None) is not None:
        lines.append(f"- 흡연 여부: {'예' if profile.is_smoker else '아니오'}")
    if getattr(profile, "is_hospitalized", None) is not None:
        lines.append(f"- 입원 여부: {'예' if profile.is_hospitalized else '아니오'}")
    if getattr(profile, "avg_sleep_hours_per_day", None):
        lines.append(f"- 평균 수면 시간: {profile.avg_sleep_hours_per_day}시간")
    if getattr(profile, "avg_exercise_minutes_per_day", None):
        lines.append(f"- 평균 운동 시간: {profile.avg_exercise_minutes_per_day}분")
    if getattr(profile, "avg_alcohol_bottles_per_week", None):
        lines.append(f"- 주간 음주량: {profile.avg_alcohol_bottles_per_week}병")
    if getattr(profile, "avg_cig_packs_per_week", None):
        lines.append(f"- 주간 흡연량: {profile.avg_cig_packs_per_week}갑")

    return "\n".join(lines) if lines else "등록된 건강 프로필 없음"


# 기본 약물 텍스트 구성
def _build_meds_text(meds: list[dict[str, Any]]) -> str:
    if not meds:
        return "등록된 확정 복용 약 없음"

    lines: list[str] = []
    for med in meds:
        display_name = med.get("display_name") or "약 이름 없음"
        dosage = med.get("dosage")
        route = med.get("route")
        notes = med.get("notes")

        chunks = [display_name]
        if dosage:
            chunks.append(f"용량={dosage}")
        if route:
            chunks.append(f"투여경로={route}")
        if notes:
            chunks.append(f"메모={notes}")

        lines.append("- " + " / ".join(chunks))

    return "\n".join(lines)


# 캐시 기반 약물 근거 텍스트 구성
def _build_cache_grounding_text(meds: list[dict[str, Any]]) -> str:
    if not meds:
        return "약물 캐시 정보 없음"

    blocks: list[str] = []

    for med in meds:
        info = med.get("drug_info") or {}
        catalog = med.get("drug_catalog") or {}
        name = med.get("display_name") or info.get("drug_name_display") or "약 이름 없음"

        lines: list[str] = [f"[약물 기본 정보] {name}"]

        if info.get("efficacy"):
            lines.append(f"- 효능/효과: {info['efficacy']}")
        if info.get("dosage_info"):
            lines.append(f"- 사용법: {info['dosage_info']}")
        if info.get("precautions"):
            lines.append(f"- 주의사항: {info['precautions']}")
        if info.get("interactions"):
            lines.append(f"- 상호작용: {info['interactions']}")
        if info.get("side_effects"):
            lines.append(f"- 부작용: {info['side_effects']}")
        if info.get("storage_method"):
            lines.append(f"- 보관법: {info['storage_method']}")
        if catalog.get("ingredients"):
            lines.append(f"- 성분: {catalog['ingredients']}")
        if catalog.get("warnings"):
            lines.append(f"- 경고: {catalog['warnings']}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "약물 캐시 정보 없음"


# 복약 일정 텍스트 구성
def _build_schedule_text(schedules: list[dict[str, Any]], meds: list[dict[str, Any]]) -> str:
    if not schedules:
        return "등록된 복약 일정 없음"

    med_name_map: dict[int, str] = {}
    for med in meds:
        patient_med_id = med.get("patient_med_id")
        display_name = med.get("display_name")
        if patient_med_id is not None and display_name:
            med_name_map[int(patient_med_id)] = str(display_name)

    lines: list[str] = []
    for schedule in schedules:
        patient_med_id = int(schedule.get("patient_med_id"))
        med_name = med_name_map.get(patient_med_id, f"patient_med_id={patient_med_id}")
        times = schedule.get("times") or []

        if not times:
            lines.append(f"- {med_name}: 시간 정보 없음")
            continue

        for time_item in times:
            time_text = time_item.get("time_of_day") or "시간 미설정"
            days_text = time_item.get("days_of_week") or "요일 정보 없음"
            lines.append(f"- {med_name}: 시간={time_text} / 요일={days_text}")

    return "\n".join(lines) if lines else "등록된 복약 일정 없음"


# MFDS 근거 텍스트 구성
def _build_mfds_grounding_text(mfds_evidence: list[dict[str, Any]]) -> str:
    if not mfds_evidence:
        return "MFDS 보강 정보 없음"

    blocks: list[str] = []

    for item in mfds_evidence:
        query_name = item.get("query_name") or item.get("drug_name_display") or "약물"
        lines = [f"[MFDS 보강] {query_name}"]

        if item.get("efficacy"):
            lines.append(f"- 효능/효과: {item['efficacy']}")
        if item.get("dosage_info"):
            lines.append(f"- 사용법: {item['dosage_info']}")
        if item.get("precautions"):
            lines.append(f"- 주의사항: {item['precautions']}")
        if item.get("interactions"):
            lines.append(f"- 상호작용: {item['interactions']}")
        if item.get("side_effects"):
            lines.append(f"- 부작용: {item['side_effects']}")
        if item.get("storage_method"):
            lines.append(f"- 보관법: {item['storage_method']}")

        contraindications = item.get("contraindications") or []
        if contraindications:
            lines.append(f"- 금기/주의: {' / '.join(str(x) for x in contraindications if x)}")

        dur_safety = item.get("dur_safety") or {}

        if dur_safety.get("age_taboo"):
            lines.append(f"- 연령금기: {dur_safety['age_taboo']}")
        if dur_safety.get("oldman_care"):
            lines.append(f"- 노인주의: {dur_safety['oldman_care']}")
        if dur_safety.get("pregnant_taboo"):
            lines.append(f"- 임부금기: {dur_safety['pregnant_taboo']}")
        if dur_safety.get("combo_taboo"):
            lines.append(f"- 병용금기: {dur_safety['combo_taboo']}")
        if dur_safety.get("dose_care"):
            lines.append(f"- 용량주의: {dur_safety['dose_care']}")
        if dur_safety.get("period_care"):
            lines.append(f"- 투여기간주의: {dur_safety['period_care']}")
        if dur_safety.get("efficacy_group_overlap"):
            lines.append(f"- 효능군중복주의: {dur_safety['efficacy_group_overlap']}")

        max_daily_dose = item.get("max_daily_dose") or {}
        dose_bits = [
            max_daily_dose.get("ingredient_name"),
            max_daily_dose.get("max_daily_dose"),
            max_daily_dose.get("unit"),
            max_daily_dose.get("route"),
            max_daily_dose.get("dosage_form"),
        ]
        dose_bits = [str(x) for x in dose_bits if x]
        if dose_bits:
            lines.append(f"- 1일 최대투여량: {' / '.join(dose_bits)}")

        blocks.append("\n".join(lines))

    return "\n\n".join(blocks) if blocks else "MFDS 보강 정보 없음"


# KIDS 근거 텍스트 구성
def _build_kids_grounding_text(kids_evidence: list[dict[str, Any]]) -> str:
    if not kids_evidence:
        return "KIDS 보강 정보 없음"

    blocks: list[str] = []
    for item in kids_evidence:
        blocks.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(blocks)


# RAG 근거 텍스트 구성
def _build_rag_grounding_text(rag_context: list[dict[str, Any]]) -> str:
    if not rag_context:
        return "RAG 참고 근거 없음"

    blocks: list[str] = []
    for item in rag_context:
        blocks.append(json.dumps(item, ensure_ascii=False))
    return "\n\n".join(blocks)


# system prompt 렌더링
def _build_system_prompt(audience: str) -> str:
    template = _read_prompt_template("guide_system_prompt.txt")
    return template.format(
        audience=audience,
        disclaimer=DISCLAIMER,
    )


# user prompt 렌더링
def _build_user_prompt(
    *,
    bundle: GuideContextBundle,
    meds_text: str,
    schedule_text: str,
    cache_grounding_text: str,
    mfds_grounding_text: str,
    kids_grounding_text: str,
    rag_grounding_text: str,
) -> str:
    template = _read_prompt_template("guide_user_prompt.txt")
    profile_text = _build_profile_text(bundle.profile)

    return template.format(
        profile_text=profile_text,
        meds_text=meds_text,
        schedule_text=schedule_text,
        cache_grounding_text=cache_grounding_text,
        mfds_grounding_text=mfds_grounding_text,
        kids_grounding_text=kids_grounding_text,
        rag_grounding_text=rag_grounding_text,
    )


# OpenAI 호출
async def _call_openai_json(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = _get_openai_key()
    model = _get_openai_model()

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"].strip()
    return json.loads(content)


# 실패 상태 저장
async def _is_guide_ready_notification_enabled(user_id: int) -> bool:
    settings = await NotificationSettings.get_or_none(user_id=user_id)
    if settings is None:
        return True
    return bool(settings.guide_ready)


async def _guide_ready_notification_exists(*, user_id: int, reminder_key: str) -> bool:
    return await Notification.filter(
        user_id=user_id,
        type="guide_ready",
        payload_json__contains=f'"reminder_key":"{reminder_key}"',
    ).exists()


async def _notify_guide_ready(guide: Guide) -> None:
    patient = await Patient.get_or_none(id=guide.patient_id)
    if patient is None:
        return

    recipients: set[int] = set()
    if getattr(patient, "user_id", None):
        recipients.add(int(patient.user_id))

    links = await CaregiverPatientLink.filter(
        patient_id=guide.patient_id,
        status="active",
        revoked_at__isnull=True,
    ).all()
    for link in links:
        caregiver_user_id = getattr(link, "caregiver_user_id", None)
        if caregiver_user_id:
            recipients.add(int(caregiver_user_id))

    if not recipients:
        return

    reminder_key = f"guide_ready:{guide.document_id}:{guide.id}"
    title = "새 가이드가 준비되었어요" if int(guide.version or 1) > 1 else "복약 가이드가 준비되었어요"
    body = "AI 가이드 생성이 완료되었어요. 알림센터에서 내용을 확인해 주세요."
    payload = {
        "guide_id": int(guide.id),
        "document_id": int(guide.document_id),
        "patient_id": int(guide.patient_id),
        "version": int(guide.version or 1),
        "reminder_key": reminder_key,
    }
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    for user_id in recipients:
        if not await _is_guide_ready_notification_enabled(user_id):
            continue
        if await _guide_ready_notification_exists(user_id=user_id, reminder_key=reminder_key):
            continue

        notification = await Notification.create(
            user_id=user_id,
            patient_id=guide.patient_id,
            type="guide_ready",
            title=title,
            body=body,
            payload_json=payload_json,
            sent_at=None,
        )
        await enqueue_send_notification(notification.id)


async def _mark_failed(guide: Guide, *, code: str, message: str) -> None:
    guide.status = GuideStatus.FAILED
    guide.failure_code = code
    guide.failure_message = message[:4000]
    await guide.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])


# 가이드 생성 task
async def generate_guide(guide_id: int) -> None:
    guide = await Guide.get(id=guide_id)

    try:
        document_id = getattr(guide, "document_id", None)
        if document_id is None:
            raise ValueError("guide.document_id is missing")

        bundle = await GuideService.build_generation_context(document_id=int(document_id))

        audience = _audience_from_profile(bundle.profile)
        meds_text = _build_meds_text(bundle.meds)
        schedule_text = _build_schedule_text(bundle.schedules, bundle.meds)
        cache_grounding_text = _build_cache_grounding_text(bundle.meds)
        mfds_grounding_text = _build_mfds_grounding_text(bundle.mfds_evidence)
        kids_grounding_text = _build_kids_grounding_text(bundle.kids_evidence)
        rag_grounding_text = _build_rag_grounding_text(bundle.rag_context)

        system_prompt = _build_system_prompt(audience)
        user_prompt = _build_user_prompt(
            bundle=bundle,
            meds_text=meds_text,
            schedule_text=schedule_text,
            cache_grounding_text=cache_grounding_text,
            mfds_grounding_text=mfds_grounding_text,
            kids_grounding_text=kids_grounding_text,
            rag_grounding_text=rag_grounding_text,
        )

        payload = await _call_openai_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        validated = validate_guide_payload(payload)

        guide.content_text = validated["content_text"]
        guide.content_json = validated["content_json"]
        guide.caregiver_summary = validated["caregiver_summary"]
        guide.disclaimer = validated["disclaimer"]
        guide.status = GuideStatus.DONE
        guide.failure_code = None
        guide.failure_message = None
        await guide.save(
            update_fields=[
                "content_text",
                "content_json",
                "caregiver_summary",
                "disclaimer",
                "status",
                "failure_code",
                "failure_message",
                "updated_at",
            ]
        )
        await _notify_guide_ready(guide)

        logger.info("guide generated guide_id=%s", guide.id)

    except GuideServiceError as exc:
        await _mark_failed(guide, code=exc.code, message=exc.message)
        logger.exception("guide generation failed guide_id=%s code=%s", guide.id, exc.code)
        raise
    except httpx.HTTPError as exc:
        await _mark_failed(guide, code="OPENAI_HTTP_ERROR", message=str(exc))
        logger.exception("guide generation failed guide_id=%s code=OPENAI_HTTP_ERROR", guide.id)
        raise
    except json.JSONDecodeError as exc:
        await _mark_failed(guide, code="INVALID_LLM_JSON", message=str(exc))
        logger.exception("guide generation failed guide_id=%s code=INVALID_LLM_JSON", guide.id)
        raise
    except ValueError as exc:
        await _mark_failed(guide, code="GUIDE_VALIDATION_FAILED", message=str(exc))
        logger.exception("guide generation failed guide_id=%s code=GUIDE_VALIDATION_FAILED", guide.id)
        raise
    except RuntimeError as exc:
        await _mark_failed(guide, code="WORKER_CONFIG_ERROR", message=str(exc))
        logger.exception("guide generation failed guide_id=%s code=WORKER_CONFIG_ERROR", guide.id)
        raise
