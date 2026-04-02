from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import redis.asyncio as redis

from app.dtos.chat import (
    ChatFeedbackCreateData,
    ChatFeedbackCreateResponse,
    ChatMessageCreateData,
    ChatMessageCreateResponse,
    ChatMessageItem,
    ChatMessageListData,
    ChatMessageListResponse,
    ChatSessionCreateData,
    ChatSessionCreateResponse,
    RequesterRole,
)
from app.models.chat import ChatFeedback, ChatMessage, ChatSession, ChatSessionMemory
from app.models.guides import Guide
from app.models.hospital_schedules import HospitalSchedule
from app.models.patients import Patient, PatientProfile
from app.models.users import User
from app.services.chat.checklist_reply import (
    answer_allergy_food_intent as _answer_allergy_food_intent_impl,
)
from app.services.chat.checklist_reply import (
    answer_caregiver_check_intent as _answer_caregiver_check_intent_impl,
)
from app.services.chat.checklist_reply import (
    answer_self_check_intent as _answer_self_check_intent_impl,
)
from app.services.chat.condition_interaction import (
    answer_condition_general_intent as _answer_condition_general_intent_impl,
)
from app.services.chat.condition_interaction import (
    build_external_interaction_points as _build_external_interaction_points_impl,
)
from app.services.chat.condition_interaction import (
    build_interaction_focus_points as _build_interaction_focus_points_impl,
)
from app.services.chat.context_builder import build_patient_chat_context as _build_patient_chat_context_impl
from app.services.chat.context_loader import (
    build_kids_evidence as _build_kids_evidence,
)
from app.services.chat.context_loader import (
    get_active_dur_alerts as _get_active_dur_alerts,
)
from app.services.chat.context_loader import (
    get_active_meds as _get_active_meds,
)
from app.services.chat.context_loader import (
    get_active_schedules as _get_active_schedules,
)
from app.services.chat.context_loader import (
    get_hospital_schedules as _get_hospital_schedules,
)
from app.services.chat.context_loader import (
    get_latest_done_guide as _get_latest_done_guide,
)
from app.services.chat.context_loader import (
    get_profile as _get_profile,
)
from app.services.chat.context_loader import (
    get_recent_adherence_summary as _get_recent_adherence_summary,
)
from app.services.chat.context_loader import (
    get_session_memory as _get_session_memory,
)
from app.services.chat.conversation_reply import (
    answer_daily_chat as _answer_daily_chat_impl,
)
from app.services.chat.conversation_reply import (
    answer_med_time_split_intent as _answer_med_time_split_intent_impl,
)
from app.services.chat.conversation_reply import (
    answer_session_summary_intent as _answer_session_summary_intent_impl,
)
from app.services.chat.direct_reply import (
    build_deterministic_answer_parts as _build_deterministic_answer_parts_impl,
)
from app.services.chat.direct_reply import (
    render_planned_reply as _render_planned_reply_impl,
)
from app.services.chat.entity_extraction import (
    extract_external_drug_name as _extract_external_drug_name,
)
from app.services.chat.entity_extraction import (
    extract_target_med as _extract_target_med,
)
from app.services.chat.external_reply import (
    answer_external_interaction_intent as _answer_external_interaction_intent_impl,
)
from app.services.chat.external_reply import (
    answer_external_med_intent as _answer_external_med_intent_impl,
)
from app.services.chat.external_reply import (
    answer_medication_caution_intent as _answer_medication_caution_intent_impl,
)
from app.services.chat.fact_summary import build_fact_summary as _build_fact_summary_impl
from app.services.chat.intent_classifier import (
    analyze_intents as _classify_intents,
)
from app.services.chat.intent_classifier import (
    detect_intent as _classify_primary_intent,
)
from app.services.chat.intent_order import normalize_intent_order as _normalize_intent_order_impl
from app.services.chat.intents import EXTERNAL_EVIDENCE_INTENTS, FAST_SYNC_INTENTS
from app.services.chat.keywords import (
    _AFFIRMATIVE_SHORT_REPLIES,
    _BOT_CAPABILITY_KEYWORDS,
    _CONDITION_MED_KEYWORDS,
    _DIRECT_EMERGENCY_SYMPTOM_KEYWORDS,
    _EMERGENCY_EXPLORATION_KEYWORDS,
    _FOLLOWUP_MED_REFERENCES,
    _PERSONALIZED_INTENTS,
)
from app.services.chat.med_detail_reply import answer_med_detail_intent as _answer_med_detail_intent_impl
from app.services.chat.memory_update import update_session_memory as _update_session_memory_impl
from app.services.chat.plan_policy import (
    build_record_required_reply as _build_record_required_reply_impl,
)
from app.services.chat.plan_policy import (
    harmonize_chat_plan as _harmonize_chat_plan_impl,
)
from app.services.chat.plan_policy import (
    has_required_context_for_request as _has_required_context_for_request_impl,
)
from app.services.chat.plan_policy import (
    is_personalized_request as _is_personalized_request_impl,
)
from app.services.chat.plan_policy import (
    resolve_data_readiness as _resolve_data_readiness_impl,
)
from app.services.chat.planner_utils import (
    call_chat_model as _call_chat_model_impl,
)
from app.services.chat.planner_utils import (
    fallback_reply as _fallback_reply_impl,
)
from app.services.chat.planner_utils import (
    plan_chat_question as _plan_chat_question_impl,
)
from app.services.chat.profile_guidance import (
    build_profile_guidance_points as _build_profile_guidance_points_impl,
)
from app.services.chat.profile_guidance import (
    build_profile_guidance_sections as _build_profile_guidance_sections_impl,
)
from app.services.chat.profile_reply import answer_profile_intent as _answer_profile_intent_impl
from app.services.chat.quality import (
    apply_response_contract,
    log_chat_metric,
    normalize_user_message,
)
from app.services.chat.question_analyzer import analyze_question_data as _analyze_question_data
from app.services.chat.runtime import (
    CHAT_DISCLAIMER,
    CHAT_HISTORY_TURNS,
    CHAT_MAX_MESSAGE_CHARS,
    CHAT_SLOW_CONTEXT_SECONDS,
    CHAT_SLOW_REPLY_SECONDS,
    CHAT_WORKER_QUEUE,
    REDIS_URL,
)
from app.services.chat.schedule_clarification import (
    answer_general_caution_intent as _answer_general_caution_intent_impl,
)
from app.services.chat.schedule_clarification import (
    answer_hospital_schedule_intent as _answer_hospital_schedule_intent_impl,
)
from app.services.chat.schedule_clarification import (
    build_clarification_reply as _build_clarification_reply_impl,
)
from app.services.chat.text_utils import (
    choose_korean_particle as _choose_korean_particle,
)
from app.services.chat.text_utils import (
    compact_text as _compact_text,
)
from app.services.chat.text_utils import (
    contains_any as _contains_any,
)
from app.services.chat.text_utils import (
    contains_keyword as _contains_keyword,
)
from app.services.chat.text_utils import (
    dedupe_lines as _dedupe_lines,
)
from app.services.chat.text_utils import (
    find_best_med_match as _find_best_med_match,
)
from app.services.chat.text_utils import (
    first_clean_line as _first_clean_line,
)
from app.services.chat.text_utils import (
    mask_log_value as _mask_log_value,
)
from app.services.chat.text_utils import (
    split_text_items as _split_text_items,
)
from app.services.chat.text_utils import (
    summarize_text as _summarize_text,
)
from app.services.chat.text_utils import (
    with_particle as _with_particle,
)
from app.services.chat.wellness_reply import (
    answer_lifestyle_top_intent as _answer_lifestyle_top_intent_impl,
)
from app.services.chat.wellness_reply import (
    answer_symptom_cause_intent as _answer_symptom_cause_intent_impl,
)
from app.services.kids_client import KIDSClient
from app.services.mfds import MfdsService
from app.services.rag import (
    build_rag_context,
    extract_external_blocks,
    extract_guide_blocks,
    extract_meds_blocks,
    extract_profile_blocks,
    extract_schedule_blocks,
)
from app.services.role_utils import user_has_role

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _normalize_user_message(content: str) -> str:
    return normalize_user_message(content)


def _log_chat_metric(event: str, **fields: Any) -> None:
    log_chat_metric(event=event, logger=logger, **fields)


def _apply_response_contract(*, content: str, analysis: QuestionAnalysis) -> str:
    return apply_response_contract(
        content=content,
        is_emergency=analysis.is_emergency,
        emergency_message=analysis.emergency_message,
        disclaimer=CHAT_DISCLAIMER,
    )


# keyword/intent 상수는 app.services.chat.keywords로 분리하여 관리한다.


class ChatServiceError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class PatientChatContext:
    patient_id: int
    profile: PatientProfile | None
    latest_guide: Guide | None
    meds: list[dict[str, Any]]
    schedules: list[dict[str, Any]]
    hospital_schedules: list[HospitalSchedule]
    dur_alerts: list[dict[str, Any]]
    adherence_summary: dict[str, Any]
    recent_messages: list[ChatMessage]
    session_memory: ChatSessionMemory | None
    kids_evidence: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]


@dataclass
class QuestionAnalysis:
    raw_message: str
    intents: list[str]
    primary_intent: str
    target_med: dict[str, Any] | None
    external_drug_name: str | None
    target_condition: str | None
    time_period: str | None
    is_emergency: bool
    emergency_message: str | None
    answer_mode: str


@dataclass
class ChatPlan:
    topic: str
    requested_fields: list[str]
    referenced_drug_name: str | None
    needs_clarification: bool
    clarification_question: str | None
    use_record_data: list[str]
    answer_style: str


def _harmonize_chat_plan(*, analysis: QuestionAnalysis, plan: ChatPlan | None) -> ChatPlan | None:
    return _harmonize_chat_plan_impl(analysis=analysis, plan=plan, plan_factory=ChatPlan)


# 요청자 역할 판별
async def _resolve_requester_role(user_id: int) -> RequesterRole:
    # Louis수정(코드삭제): Patient row 존재 여부만으로 역할을 판별하면 보호자+본인프로필 계정이 PATIENT로 오인됨
    if await user_has_role(user_id, "ADMIN"):
        return RequesterRole.ADMIN

    # Louis수정(기능추가): 역할 테이블 기준으로 우선 판별해 보호자가 연동 환자에 정상 접근하도록 수정
    if await user_has_role(user_id, "CAREGIVER", "GUARDIAN"):
        return RequesterRole.CAREGIVER

    if await user_has_role(user_id, "PATIENT"):
        return RequesterRole.PATIENT

    patient_exists = await Patient.filter(user_id=user_id).exists()
    if patient_exists:
        return RequesterRole.PATIENT

    return RequesterRole.ADMIN


# 프롬프트 파일 읽기
def _read_prompt_template(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise RuntimeError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")


def _has_openai_api_key() -> bool:
    return bool((os.getenv("OPENAI_API_KEY", "") or "").strip())


# 응급 키워드 감지
def _detect_emergency(message: str) -> tuple[bool, str | None]:
    normalized = (message or "").strip()
    if _contains_any(normalized, _DIRECT_EMERGENCY_SYMPTOM_KEYWORDS):
        return (
            True,
            "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요.",
        )

    if _contains_any(normalized, ["119", "응급실", "응급"]) and _contains_any(
        normalized, _EMERGENCY_EXPLORATION_KEYWORDS
    ):
        return False, None

    for keyword in ["응급실", "119"]:
        if keyword in normalized:
            return (
                True,
                "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요.",
            )
    return False, None


# 현재 연도
def date_today_year() -> int:
    from datetime import date

    return date.today().year


# 연령대 분류
def _resolve_audience(profile: PatientProfile | None) -> str:
    birth_year = getattr(profile, "birth_year", None)
    if not birth_year:
        return "adult"

    age = date_today_year() - int(birth_year)

    if age <= 12:
        return "child"
    if 13 <= age <= 18:
        return "teen"
    if age >= 65:
        return "senior"
    return "adult"


# 설명 라벨
def _audience_label(audience: str) -> str:
    if audience == "child":
        return "아이용 아주 쉬운 설명"
    if audience == "teen":
        return "청소년용 쉬운 설명"
    if audience == "senior":
        return "고령자용 주의 강화 설명"
    return "성인용 일반 설명"


# 추가 안전 문구
def _extra_safety_text(audience: str) -> str:
    if audience == "child":
        return "아이의 경우 보호자 확인이 중요하며 어려운 의학용어를 피한다."
    if audience == "teen":
        return "청소년은 이해하기 쉬운 설명으로 답하고 복약 실수를 줄이도록 돕는다."
    if audience == "senior":
        return "65세 이상은 어지러움, 낙상, 복약 시간 혼동, 보호자 확인 필요성을 함께 고려한다."
    return "제공된 근거 범위 안에서 일반 성인 기준으로 설명한다."


# 건강 프로필 텍스트 구성
def _build_profile_text(profile: PatientProfile | None) -> str:
    if not profile:
        return "등록된 건강 프로필 없음"

    lines: list[str] = []
    if getattr(profile, "birth_year", None):
        lines.append(f"- 출생연도: {profile.birth_year}")
    if getattr(profile, "sex", None):
        lines.append(f"- 성별: {profile.sex}")
    if getattr(profile, "height_cm", None) is not None:
        lines.append(f"- 키(cm): {profile.height_cm}")
    if getattr(profile, "weight_kg", None) is not None:
        lines.append(f"- 체중(kg): {profile.weight_kg}")
    if getattr(profile, "bmi", None) is not None:
        lines.append(f"- BMI: {profile.bmi}")
    if getattr(profile, "conditions", None):
        lines.append(f"- 기저질환/상태: {profile.conditions}")
    if getattr(profile, "allergies", None):
        lines.append(f"- 알레르기: {profile.allergies}")
    if getattr(profile, "notes", None):
        lines.append(f"- 메모: {profile.notes}")
    if getattr(profile, "is_smoker", None) is not None:
        lines.append(f"- 흡연 여부: {'예' if profile.is_smoker else '아니오'}")
    if getattr(profile, "avg_cig_packs_per_week", None) is not None:
        lines.append(f"- 주간 흡연량: {profile.avg_cig_packs_per_week}갑")
    if getattr(profile, "avg_alcohol_bottles_per_week", None) is not None:
        lines.append(f"- 주간 음주량: {profile.avg_alcohol_bottles_per_week}병")
    if getattr(profile, "avg_sleep_hours_per_day", None) is not None:
        lines.append(f"- 평균 수면 시간: {profile.avg_sleep_hours_per_day}시간")
    if getattr(profile, "avg_exercise_minutes_per_day", None) is not None:
        lines.append(f"- 평균 운동 시간: {profile.avg_exercise_minutes_per_day}분")
    if getattr(profile, "is_hospitalized", None) is not None:
        lines.append(f"- 입원 여부: {'예' if profile.is_hospitalized else '아니오'}")

    return "\n".join(lines) if lines else "등록된 건강 프로필 없음"


def _bmi_category_text(bmi: Any) -> str | None:
    try:
        value = float(bmi)
    except Exception:
        return None

    if value < 18.5:
        return "저체중 범위"
    if value < 23:
        return "정상 범위"
    if value < 25:
        return "과체중 범위"
    return "비만 범위"


def _build_profile_summary_lines(profile: PatientProfile) -> list[str]:
    lines: list[str] = []
    conditions = _split_text_items(getattr(profile, "conditions", None))
    allergies = _split_text_items(getattr(profile, "allergies", None))

    body_chunks: list[str] = []
    if getattr(profile, "height_cm", None) is not None:
        body_chunks.append(f"키 {profile.height_cm}cm")
    if getattr(profile, "weight_kg", None) is not None:
        body_chunks.append(f"몸무게 {profile.weight_kg}kg")
    if getattr(profile, "bmi", None) is not None:
        bmi_category = _bmi_category_text(profile.bmi)
        if bmi_category:
            body_chunks.append(f"BMI {profile.bmi}({bmi_category})")
        else:
            body_chunks.append(f"BMI {profile.bmi}")
    if body_chunks:
        lines.append(", ".join(body_chunks))

    lifestyle_chunks: list[str] = []
    if getattr(profile, "avg_sleep_hours_per_day", None) is not None:
        lifestyle_chunks.append(f"수면 {profile.avg_sleep_hours_per_day}시간")
    if getattr(profile, "avg_exercise_minutes_per_day", None) is not None:
        lifestyle_chunks.append(f"운동 {profile.avg_exercise_minutes_per_day}분")
    if getattr(profile, "is_smoker", None) is not None:
        smoker_text = "흡연 중" if profile.is_smoker else "비흡연"
        packs = getattr(profile, "avg_cig_packs_per_week", None)
        if packs is not None:
            smoker_text += f", 주간 흡연량 {packs}갑"
        lifestyle_chunks.append(smoker_text)
    if getattr(profile, "avg_alcohol_bottles_per_week", None) is not None:
        lifestyle_chunks.append(f"주간 음주량 {profile.avg_alcohol_bottles_per_week}병")
    if lifestyle_chunks:
        lines.append("생활 습관: " + ", ".join(lifestyle_chunks))

    if conditions:
        lines.append("건강 상태: " + ", ".join(conditions[:3]))
    if allergies:
        lines.append("알레르기: " + ", ".join(allergies[:3]))
    if getattr(profile, "is_hospitalized", None) is not None:
        admission_text = "입원 중" if profile.is_hospitalized else "현재 입원 기록 없음"
        if getattr(profile, "discharge_date", None):
            admission_text += f", 퇴원일 {profile.discharge_date}"
        lines.append("입원 정보: " + admission_text)
    if getattr(profile, "notes", None):
        note = _summarize_text(profile.notes, max_sentences=1)
        if note:
            lines.append("메모: " + note)

    return lines


def _build_profile_guidance_points(*, profile: PatientProfile | None, guide: Guide | None) -> list[str]:
    return _build_profile_guidance_points_impl(
        profile=profile,
        guide=guide,
        ops={
            "split_text_items": _split_text_items,
            "summarize_text": _summarize_text,
            "first_clean_line": _first_clean_line,
            "dedupe_lines": _dedupe_lines,
        },
    )


def _build_adherence_guidance_points(*, adherence_summary: dict[str, Any] | None) -> list[str]:
    if not adherence_summary:
        return []

    points: list[str] = []
    missed = int(adherence_summary.get("missed", 0) or 0)
    taken = int(adherence_summary.get("taken", 0) or 0)
    pending = int(adherence_summary.get("pending", 0) or 0)
    recent_missed_names = adherence_summary.get("recent_missed_names") or []
    recent_lines = adherence_summary.get("recent_lines") or []

    if missed > 0:
        if recent_missed_names:
            names = ", ".join(
                _dedupe_lines([str(name).strip() for name in recent_missed_names if str(name).strip()], limit=3)
            )
            points.append(
                f"최근 복약 기록에서는 놓친 약이 있어 {names}부터 다시 일정대로 챙기는지 확인하는 것이 좋습니다."
            )
        else:
            points.append("최근 복약 기록에서는 놓친 일정이 있어 미복용이 반복되지 않는지 먼저 확인하는 것이 좋습니다.")
    elif taken > 0:
        points.append(
            "최근 복약 기록상 이미 복용한 일정이 있어 현재 복약 흐름은 어느 정도 이어지고 있는 것으로 보입니다."
        )

    if pending > 0:
        points.append(
            f"아직 복용 대기 상태로 남아 있는 일정이 {pending}건 있어 오늘 남은 약도 함께 확인하는 것이 좋습니다."
        )

    for line in recent_lines[:2]:
        clean = str(line).strip()
        if clean:
            points.append("최근 복약 상태: " + clean)

    return _dedupe_lines(points, limit=3)


def _build_profile_guidance_sections(
    *,
    message: str,
    profile: PatientProfile | None,
    guide: Guide | None,
    adherence_summary: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    return _build_profile_guidance_sections_impl(
        message=message,
        profile=profile,
        guide=guide,
        adherence_summary=adherence_summary,
        ops={
            "contains_any": _contains_any,
            "split_text_items": _split_text_items,
            "first_clean_line": _first_clean_line,
            "dedupe_lines": _dedupe_lines,
            "summarize_text": _summarize_text,
            "build_adherence_guidance_points": _build_adherence_guidance_points,
        },
    )


def _build_med_adherence_points(*, med_name: str, adherence_summary: dict[str, Any] | None) -> list[str]:
    if not adherence_summary:
        return []

    compact_med = _compact_text(med_name).lower()
    recent_lines = adherence_summary.get("recent_lines") or []
    recent_missed_names = adherence_summary.get("recent_missed_names") or []
    points: list[str] = []

    if any(compact_med and compact_med in _compact_text(str(name)).lower() for name in recent_missed_names):
        points.append(f"{med_name}은 최근 복약 기록에서 놓친 이력이 있어 다음 복용 전 일정 재확인이 필요합니다.")

    for line in recent_lines:
        clean = str(line).strip()
        if compact_med and compact_med in _compact_text(clean).lower():
            points.append("최근 복약 상태: " + clean)
            if len(points) >= 2:
                break

    return _dedupe_lines(points, limit=2)


def _extract_dur_alert_points(
    *,
    dur_alerts: list[dict[str, Any]],
    med_name: str | None = None,
    limit: int = 3,
) -> list[str]:
    if not dur_alerts:
        return []

    points: list[str] = []
    compact_med = _compact_text(med_name).lower() if med_name else ""
    for alert in dur_alerts:
        patient_med_name = str(alert.get("patient_med_name") or "").strip()
        related_med_name = str(alert.get("related_patient_med_name") or "").strip()
        if compact_med:
            candidates = [_compact_text(patient_med_name).lower(), _compact_text(related_med_name).lower()]
            if compact_med not in candidates and all(compact_med not in item for item in candidates if item):
                continue

        level = str(alert.get("level") or "").strip()
        message = str(alert.get("message") or "").strip()
        alert_type = str(alert.get("alert_type") or "").strip()
        if message:
            if level:
                points.append(f"DUR {level}: {message}")
            else:
                points.append(f"DUR {message}")
        elif alert_type:
            parts = [part for part in [patient_med_name, related_med_name] if part]
            joined = " / ".join(parts)
            if joined:
                points.append(f"DUR {alert_type}: {joined}")
            else:
                points.append(f"DUR {alert_type}")

    return _dedupe_lines(points, limit=limit)


def _build_med_guidance_points(*, guide: Guide | None, med_name: str) -> list[str]:
    if not guide or not isinstance(guide.content_json, dict):
        return []

    compact_med = _compact_text(med_name).lower()
    points: list[str] = []
    for section in guide.content_json.get("sections") or []:
        title = str(section.get("title") or "").strip()
        body = str(section.get("body") or "").strip()
        full_text = f"{title}\n{body}".strip()
        if compact_med and compact_med in _compact_text(full_text).lower():
            first_line = _first_clean_line(body)
            if first_line:
                points.append(first_line)
        elif any(keyword in title for keyword in ["주의", "복약", "생활"]):
            first_line = _first_clean_line(body)
            if first_line:
                points.append(first_line)
        if len(points) >= 2:
            break
    return _dedupe_lines(points, limit=2)


# 약 정보 텍스트 구성
def _build_meds_text(meds: list[dict[str, Any]]) -> str:
    if not meds:
        return "현재 복용 약 정보 없음"

    lines: list[str] = []
    for med in meds:
        display_name = med.get("display_name") or "약 이름 없음"
        dosage = med.get("dosage")
        route = med.get("route")

        chunks = [display_name]
        if dosage:
            chunks.append(f"용량={dosage}")
        if route:
            chunks.append(f"경로={route}")

        lines.append("- " + " / ".join(chunks))

    return "\n".join(lines)


# 시간 문구 변환
def _humanize_time(time_text: str | None) -> str:
    if not time_text:
        return "시간 미설정"

    raw = str(time_text).strip()
    hour = None
    minute = 0

    try:
        parts = raw.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        return raw

    if hour == 0 and minute == 0:
        return "자정"
    if hour < 12:
        prefix = "오전"
        shown_hour = 12 if hour == 0 else hour
    elif hour == 12:
        prefix = "정오"
        shown_hour = 12
    else:
        prefix = "오후"
        shown_hour = hour - 12

    if prefix == "정오":
        return "정오" if minute == 0 else f"정오 {minute}분"

    if minute == 0:
        return f"{prefix} {shown_hour}시"
    return f"{prefix} {shown_hour}시 {minute}분"


# 요일 문구 변환
def _humanize_days(days_text: str | None) -> str:
    if not days_text:
        return "요일 정보 없음"

    normalized = str(days_text).replace(" ", "")
    upper_normalized = normalized.upper()
    if normalized in {"1,2,3,4,5,6,7", "1,2,3,4,5,6,7,"} or upper_normalized in {
        "MON,TUE,WED,THU,FRI,SAT,SUN",
        "MON,TUE,WED,THU,FRI,SAT,SUN,",
    }:
        return "매일"

    day_map = {
        "1": "월",
        "2": "화",
        "3": "수",
        "4": "목",
        "5": "금",
        "6": "토",
        "7": "일",
        "MON": "월",
        "TUE": "화",
        "WED": "수",
        "THU": "목",
        "FRI": "금",
        "SAT": "토",
        "SUN": "일",
        "월": "월",
        "화": "화",
        "수": "수",
        "목": "목",
        "금": "금",
        "토": "토",
        "일": "일",
    }
    items = [day_map.get(x.upper(), day_map.get(x, x)) for x in normalized.split(",") if x]
    return ",".join(items) if items else "요일 정보 없음"


def _format_datetime_korean(value: Any) -> str:
    if value is None:
        return "일정 시간 미정"
    try:
        hour = int(value.strftime("%H"))
        minute = int(value.strftime("%M"))
        date_part = value.strftime("%Y-%m-%d")
    except Exception:
        return str(value)

    if hour == 0 and minute == 0:
        time_part = "자정"
    elif hour < 12:
        time_part = f"오전 {12 if hour == 0 else hour}시"
    elif hour == 12:
        time_part = "정오" if minute == 0 else f"정오 {minute}분"
    else:
        time_part = f"오후 {hour - 12}시"

    if minute and hour != 12:
        time_part += f" {minute}분"

    return f"{date_part} {time_part}"


# 일정 텍스트 구성
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

        for item in times:
            time_label = _humanize_time(item.get("time_of_day"))
            days_label = _humanize_days(item.get("days_of_week"))

            if days_label == "요일 정보 없음" and time_label == "시간 미설정":
                lines.append(f"- {med_name}: 복용 시간 정보가 등록되어 있지 않습니다.")
            elif days_label == "요일 정보 없음":
                lines.append(f"- {med_name}: {time_label}에 복용하도록 기록되어 있습니다.")
            elif time_label == "시간 미설정":
                lines.append(f"- {med_name}: {days_label} 복용으로 기록되어 있으나 시간 정보는 없습니다.")
            elif days_label == "매일":
                lines.append(f"- {med_name}: 매일 {time_label}")
            else:
                lines.append(f"- {med_name}: {days_label} {time_label}")

    return "\n".join(lines) if lines else "등록된 복약 일정 없음"


def _build_hospital_schedule_text(hospital_schedules: list[HospitalSchedule]) -> str:
    if not hospital_schedules:
        return "등록된 병원 일정 없음"

    lines: list[str] = []
    for item in hospital_schedules:
        title = str(getattr(item, "title", "") or "병원 일정").strip()
        hospital_name = str(getattr(item, "hospital_name", "") or "").strip()
        location = str(getattr(item, "location", "") or "").strip()
        scheduled_at = _format_datetime_korean(getattr(item, "scheduled_at", None))
        line = f"- {scheduled_at}: {title}"
        if hospital_name:
            line += f" / {hospital_name}"
        if location:
            line += f" / {location}"
        lines.append(line)
    return "\n".join(lines)


def _build_hospital_schedule_brief(hospital_schedules: list[HospitalSchedule]) -> str:
    if not hospital_schedules:
        return "병원 일정 없음"
    lines: list[str] = []
    for item in hospital_schedules[:3]:
        title = str(getattr(item, "title", "") or "병원 일정").strip()
        scheduled_at = _format_datetime_korean(getattr(item, "scheduled_at", None))
        hospital_name = str(getattr(item, "hospital_name", "") or "").strip()
        chunk = f"{scheduled_at} {title}"
        if hospital_name:
            chunk += f" / {hospital_name}"
        lines.append(chunk)
    return " ; ".join(lines)


# 최신 guide 텍스트 구성
def _build_guide_text(guide: Guide | None) -> str:
    if not guide:
        return "최신 guide 없음"

    sections: list[str] = []
    if guide.content_text:
        sections.append(f"[guide 본문]\n{guide.content_text}")
    if isinstance(guide.content_json, dict):
        sections.append(f"[guide 구조화]\n{json.dumps(guide.content_json, ensure_ascii=False)}")
    if isinstance(guide.caregiver_summary, dict):
        sections.append(f"[caregiver summary]\n{json.dumps(guide.caregiver_summary, ensure_ascii=False)}")

    return "\n\n".join(sections) if sections else "최신 guide 없음"


# 최근 대화 텍스트 구성
def _build_history_text(messages: list[ChatMessage]) -> str:
    if not messages:
        return "이전 대화 없음"

    lines: list[str] = []
    for msg in messages:
        lines.append(f"- {msg.role}: {msg.content}")
    return "\n".join(lines)


def _build_recent_history_for_planner(messages: list[ChatMessage]) -> str:
    if not messages:
        return "이전 대화 없음"

    recent = messages[-6:]
    lines: list[str] = []
    for msg in recent:
        role = "user" if msg.role == "user" else "assistant"
        lines.append(f"- {role}: {msg.content}")
    return "\n".join(lines)


def _build_session_memory_text(memory: ChatSessionMemory | None) -> str:
    if not memory:
        return "구조화 메모리 없음"

    lines: list[str] = []
    if getattr(memory, "recent_topic", None):
        lines.append(f"- 최근 주제: {memory.recent_topic}")
    if getattr(memory, "recent_drug_name", None):
        lines.append(f"- 최근 현재 약: {memory.recent_drug_name}")
    if getattr(memory, "recent_external_drug_name", None):
        lines.append(f"- 최근 외부 약: {memory.recent_external_drug_name}")
    if getattr(memory, "recent_profile_focus", None):
        lines.append(f"- 최근 프로필 초점: {memory.recent_profile_focus}")
    if getattr(memory, "recent_hospital_focus", None):
        lines.append(f"- 최근 병원 일정 초점: {memory.recent_hospital_focus}")
    if getattr(memory, "pending_clarification", None):
        lines.append(f"- 대기 중 명확화: {memory.pending_clarification}")
    if getattr(memory, "clarification_question", None):
        lines.append(f"- 직전 확인 질문: {memory.clarification_question}")
    return "\n".join(lines) if lines else "구조화 메모리 없음"


async def _update_session_memory(
    *,
    session_id: int,
    analysis: QuestionAnalysis,
    plan: ChatPlan | None,
    assistant_content: str,
    context: PatientChatContext,
) -> None:
    await _update_session_memory_impl(
        session_id=session_id,
        analysis=analysis,
        plan=plan,
        assistant_content=assistant_content,
        context=context,
        ops={
            "memory_model": ChatSessionMemory,
            "contains_any": _contains_any,
        },
    )


# KIDS evidence 텍스트 구성
def _build_kids_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "KIDS 안전성 근거 없음"
    return json.dumps(items, ensure_ascii=False)


# RAG context 텍스트 구성
def _build_rag_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "RAG 참고 근거 없음"
    return json.dumps(items, ensure_ascii=False)


# RAG용 텍스트 블록 추가 헬퍼
def _append_rag_block(blocks: list[dict[str, Any]], *, source: str, title: str, content: str) -> None:
    text = (content or "").strip()
    if not text:
        return
    blocks.append(
        {
            "source": source,
            "title": title,
            "content": text,
        }
    )


# 최신 guide에서 RAG 블록 추출
def _extract_guide_rag_blocks(guide: Guide | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not guide:
        return blocks

    if guide.content_text:
        _append_rag_block(
            blocks,
            source="guide_text",
            title="최신 가이드 본문",
            content=guide.content_text,
        )

    if isinstance(guide.content_json, dict):
        sections = guide.content_json.get("sections") or []
        for section in sections:
            title = str(section.get("title") or "가이드 섹션")
            body = str(section.get("body") or "")
            _append_rag_block(
                blocks,
                source="guide_section",
                title=title,
                content=body,
            )

    if isinstance(guide.caregiver_summary, dict):
        _append_rag_block(
            blocks,
            source="guide_caregiver_summary",
            title="보호자 요약",
            content=json.dumps(guide.caregiver_summary, ensure_ascii=False),
        )

    return blocks


# 프로필에서 RAG 블록 추출
def _extract_profile_rag_blocks(profile: PatientProfile | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not profile:
        return blocks

    profile_map = {
        "흡연 정보": getattr(profile, "avg_cig_packs_per_week", None),
        "음주 정보": getattr(profile, "avg_alcohol_bottles_per_week", None),
        "수면 정보": getattr(profile, "avg_sleep_hours_per_day", None),
        "운동 정보": getattr(profile, "avg_exercise_minutes_per_day", None),
        "기저질환": getattr(profile, "conditions", None),
        "알레르기": getattr(profile, "allergies", None),
        "메모": getattr(profile, "notes", None),
    }

    for title, value in profile_map.items():
        if value is not None and str(value).strip():
            _append_rag_block(
                blocks,
                source="profile",
                title=title,
                content=str(value),
            )

    return blocks


# 스케줄에서 RAG 블록 추출
def _extract_schedule_rag_blocks(meds: list[dict[str, Any]], schedules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    schedule_text = _build_schedule_text(schedules, meds)
    if schedule_text != "등록된 복약 일정 없음":
        _append_rag_block(
            blocks,
            source="schedule",
            title="복약 일정",
            content=schedule_text,
        )
    return blocks


# 약 정보에서 RAG 블록 추출
def _extract_meds_rag_blocks(meds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    meds_text = _build_meds_text(meds)
    if meds_text != "현재 복용 약 정보 없음":
        _append_rag_block(
            blocks,
            source="meds",
            title="현재 복용 약",
            content=meds_text,
        )
    return blocks


# RAG hook (MVP)
async def _build_rag_context(
    *,
    intent: str,
    latest_guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    profile: PatientProfile | None,
    kids_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    guide_blocks = extract_guide_blocks(latest_guide)
    profile_blocks = extract_profile_blocks(profile)
    schedule_blocks = extract_schedule_blocks(_build_schedule_text(schedules, meds))
    meds_blocks = extract_meds_blocks(_build_meds_text(meds))
    external_blocks = extract_external_blocks(
        mfds_evidence=[],
        kids_evidence=kids_evidence,
    )

    return build_rag_context(
        intent=intent,
        guide_blocks=guide_blocks,
        profile_blocks=profile_blocks,
        schedule_blocks=schedule_blocks,
        meds_blocks=meds_blocks,
        external_blocks=external_blocks,
        limit=8,
    )


# 컨텍스트 구성
async def _build_patient_chat_context(
    *,
    session_id: int,
    patient_id: int,
    include_kids_evidence: bool = True,
) -> PatientChatContext:
    return await _build_patient_chat_context_impl(
        session_id=session_id,
        patient_id=patient_id,
        include_kids_evidence=include_kids_evidence,
        chat_history_turns=CHAT_HISTORY_TURNS,
        slow_context_seconds=CHAT_SLOW_CONTEXT_SECONDS,
        context_factory=PatientChatContext,
        logger=logger,
        log_metric=_log_chat_metric,
        now_counter=perf_counter,
        ops={
            "gather": asyncio.gather,
            "chat_message_model": ChatMessage,
            "get_profile": _get_profile,
            "get_latest_done_guide": _get_latest_done_guide,
            "get_active_meds": _get_active_meds,
            "get_active_schedules": _get_active_schedules,
            "get_hospital_schedules": _get_hospital_schedules,
            "get_active_dur_alerts": _get_active_dur_alerts,
            "get_session_memory": _get_session_memory,
            "get_recent_adherence_summary": _get_recent_adherence_summary,
            "format_datetime_korean": _format_datetime_korean,
            "build_kids_evidence": _build_kids_evidence,
        },
    )


# 질문 의도 판별
def _detect_intent(message: str) -> str:
    return _classify_primary_intent(message)


def _analyze_intents(message: str) -> list[str]:
    return _classify_intents(message)


def _analyze_question(
    *,
    message: str,
    meds: list[dict[str, Any]],
    recent_messages: list[ChatMessage],
    requester_role: RequesterRole,
    profile: PatientProfile | None,
    session_memory: ChatSessionMemory | None,
) -> QuestionAnalysis:
    result = _analyze_question_data(
        message=message,
        meds=meds,
        recent_messages=recent_messages,
        requester_role=requester_role,
        profile=profile,
        session_memory=session_memory,
        extract_target_med=_extract_target_med,
        extract_external_drug_name=_extract_external_drug_name,
        detect_emergency=_detect_emergency,
        normalize_intent_order=_normalize_intent_order,
    )
    return QuestionAnalysis(**result)


# 보호자용 관리형 응답 변환
def _to_caregiver_style(*, answer: str, audience: str) -> str:
    text = str(answer or "").strip()
    if audience == "senior" and "낙상" not in text and ("어지러" in text or "혈압" in text or "보행" in text):
        text += "\n어지러움이나 보행 불안정이 있으면 낙상 위험도 함께 확인해 주세요."
    return text


# 프로필 기반 직접 응답
def _answer_profile_intent(
    *,
    intent: str,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return _answer_profile_intent_impl(
        intent=intent,
        profile=profile,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "bmi_category_text": _bmi_category_text,
            "build_profile_summary_lines": _build_profile_summary_lines,
            "split_text_items": _split_text_items,
        },
    )


def _answer_profile_guidance_intent(
    *,
    message: str,
    profile: PatientProfile | None,
    guide: Guide | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not profile and not guide:
        return None

    current_points, general_points, next_points = _build_profile_guidance_sections(
        message=message,
        profile=profile,
        guide=guide,
        adherence_summary=adherence_summary,
    )

    if not current_points and not general_points and not next_points:
        return None

    base = _compose_medical_sections(
        current_record_points=current_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 현재 복용 약 목록 직접 응답
def _answer_med_list_intent(
    *,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if not meds:
        base = f"{target_label} 기준으로 현재 확인되는 복용 약 정보가 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    med_lines: list[str] = []
    for med in meds:
        name = med.get("display_name") or "약 이름 없음"
        dosage = med.get("dosage")
        notes = med.get("notes")
        chunk = name
        if dosage:
            chunk += f" {dosage}"
        if notes:
            chunk += f" ({notes})"
        med_lines.append(f"- {chunk}")

    base = f"{target_label} 기준으로 현재 복용 중인 약은 다음과 같습니다.\n" + "\n".join(med_lines)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _has_required_context_for_request(
    *,
    analysis: QuestionAnalysis,
    plan: ChatPlan | None,
    context: PatientChatContext,
) -> bool:
    return _has_required_context_for_request_impl(analysis=analysis, plan=plan, context=context)


def _resolve_data_readiness(context: PatientChatContext) -> str:
    return _resolve_data_readiness_impl(context)


def _is_personalized_request(*, analysis: QuestionAnalysis, plan: ChatPlan | None) -> bool:
    return _is_personalized_request_impl(analysis=analysis, plan=plan, personalized_intents=set(_PERSONALIZED_INTENTS))


def _build_record_required_reply(
    *,
    analysis: QuestionAnalysis,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _build_record_required_reply_impl(
        analysis=analysis,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
        },
    )


async def _lookup_external_med_info(drug_name: str) -> dict[str, Any]:
    result: dict[str, Any] = {"mfds": None, "kids": []}
    mfds_service = MfdsService()
    kids_client = KIDSClient()
    normalized_query = _compact_text(drug_name).lower()

    try:
        mfds_response = await mfds_service.search_easy_drug_info(drug_name=drug_name, num_of_rows=1)
        if mfds_response.items:
            for item in mfds_response.items:
                item_name = _compact_text(getattr(item, "item_name", "")).lower()
                if normalized_query and item_name and (normalized_query in item_name or item_name in normalized_query):
                    result["mfds"] = item
                    break
    except Exception:
        logger.exception("external med mfds lookup failed drug=%s", _mask_log_value(drug_name))

    try:
        if kids_client.is_enabled():
            kids_items = await kids_client.search_safety_evidence(drug_name)
            filtered_kids: list[dict[str, Any]] = []
            for item in kids_items:
                content = _compact_text(str(item.get("content") or "")).lower()
                if normalized_query and content and normalized_query in content:
                    filtered_kids.append(item)
            result["kids"] = filtered_kids[:5]
    except Exception:
        logger.exception("external med kids lookup failed drug=%s", _mask_log_value(drug_name))

    return result


def _build_external_drug_text(*, drug_name: str | None, lookup: dict[str, Any] | None) -> str:
    clean_name = str(drug_name or "").strip()
    if not clean_name:
        return "질문 관련 외부 약 정보 없음"

    if not lookup:
        return f"- 질문한 외부 약 이름: {clean_name}"

    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []
    parts = [f"- 질문한 외부 약 이름: {clean_name}"]

    if mfds_item:
        item_name = str(getattr(mfds_item, "item_name", "") or clean_name).strip()
        efficacy = _first_clean_line(getattr(mfds_item, "efficacy", None))
        precautions = _first_clean_line(getattr(mfds_item, "precautions", None))
        dosage_info = _first_clean_line(getattr(mfds_item, "dosage_info", None))
        if item_name:
            parts.append(f"- MFDS 약 이름: {item_name}")
        if efficacy:
            parts.append(f"- MFDS 용도: {efficacy}")
        if precautions:
            parts.append(f"- MFDS 주의사항: {precautions}")
        if dosage_info:
            parts.append(f"- MFDS 복용 참고: {dosage_info}")

    if kids_items:
        first_kids = _first_clean_line(kids_items[0].get("content"))
        if first_kids:
            parts.append(f"- KIDS 안전 근거: {first_kids}")

    if len(parts) == 1:
        parts.append("- 외부 의약 정보 근거는 아직 직접 확인되지 않았습니다.")

    return "\n".join(parts)


def _should_prefer_llm(*, analysis: QuestionAnalysis) -> bool:
    return analysis.answer_mode in {"record_counseling", "general_counseling", "condition_counseling"}


def _answer_med_time_split_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_med_time_split_intent_impl(
        meds=meds,
        schedules=schedules,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "humanize_time": _humanize_time,
        },
    )


def _answer_med_regularity_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    schedule_med_ids = {schedule.get("patient_med_id") for schedule in schedules}
    lines: list[str] = []
    for med in meds:
        name = str(med.get("display_name") or "해당 약").strip()
        notes = str(med.get("notes") or "").strip()
        patient_med_id = med.get("patient_med_id")
        if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
            lines.append(f"- {name}: 필요 시 복용으로 보는 것이 자연스럽습니다.")
        elif patient_med_id in schedule_med_ids or any(
            keyword in notes for keyword in ["식후 복용", "취침 전", "기상 직후", "아침", "저녁"]
        ):
            lines.append(f"- {name}: 기록상 매일 정해진 시점에 복용하는 약으로 보입니다.")
        else:
            lines.append(f"- {name}: 현재 정보만으로 매일 복용 여부를 단정하기는 어렵습니다.")

    base = f"{target_label} 기준으로 매일 복용 여부를 보면 다음과 같습니다.\n" + "\n".join(lines)
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_med_prn_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    matched = _extract_target_med(message=message, meds=meds, recent_messages=recent_messages)

    if not matched:
        return None

    notes = str(matched.get("notes") or "").strip()
    name = matched.get("display_name") or "이 약"
    patient_med_id = matched.get("patient_med_id")
    matched_schedules = [schedule for schedule in schedules if schedule.get("patient_med_id") == patient_med_id]

    if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
        base = f"{target_label} 기준으로 {name}은 매일 정해진 시간에 먹는 약이라기보다 증상이 있을 때 복용하는 약으로 보는 것이 더 자연스럽습니다."
    elif matched_schedules or any(
        keyword in notes for keyword in ["식후 복용", "취침 전", "기상 직후", "아침", "저녁"]
    ):
        times: list[str] = []
        for schedule in matched_schedules:
            for item in schedule.get("times") or []:
                time_label = _humanize_time(item.get("time_of_day"))
                if time_label not in times:
                    times.append(time_label)
        if times:
            base = f"{target_label} 기준으로 {name}은 기록상 매일 복용하는 약으로 보는 것이 자연스럽습니다. 현재 등록된 시간은 {', '.join(times[:3])}입니다."
        else:
            base = f"{target_label} 기준으로 {name}은 메모와 일정상 매일 정해진 시점에 복용하는 약으로 보는 것이 자연스럽습니다."
    elif notes:
        base = f"{target_label} 기준으로 {name}은 메모상 `{notes}`로 기록되어 있습니다. 정시 복용 여부는 처방 의도와 문서 내용을 함께 확인하는 것이 좋습니다."
    else:
        base = f"{target_label} 기준으로 {name}의 매일 복용 여부를 단정할 근거는 부족합니다. 확정 문서와 처방 지시를 함께 확인해 주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_med_detail_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    session_memory: ChatSessionMemory | None = None,
    matched_med: dict[str, Any] | None = None,
    dur_alerts: list[dict[str, Any]] | None = None,
    adherence_summary: dict[str, Any] | None = None,
    guide: Guide | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return await _answer_med_detail_intent_impl(
        message=message,
        meds=meds,
        schedules=schedules,
        recent_messages=recent_messages,
        session_memory=session_memory,
        matched_med=matched_med,
        dur_alerts=dur_alerts,
        adherence_summary=adherence_summary,
        guide=guide,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "extract_target_med": _extract_target_med,
            "humanize_time": _humanize_time,
            "humanize_days": _humanize_days,
            "lookup_external_med_info": _lookup_external_med_info,
            "first_clean_line": _first_clean_line,
            "summarize_text": _summarize_text,
            "extract_dur_alert_points": _extract_dur_alert_points,
            "build_med_adherence_points": _build_med_adherence_points,
            "build_med_guidance_points": _build_med_guidance_points,
            "compose_medical_sections": _compose_medical_sections,
        },
    )


# 보호자 체크포인트 직접 응답
def _answer_caregiver_check_intent(
    *,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_caregiver_check_intent_impl(
        guide=guide,
        meds=meds,
        schedules=schedules,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "build_schedule_text": _build_schedule_text,
        },
    )


def _answer_self_check_intent(
    *,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_self_check_intent_impl(
        guide=guide,
        meds=meds,
        schedules=schedules,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "build_schedule_text": _build_schedule_text,
        },
    )


def _answer_allergy_food_intent(
    *,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_allergy_food_intent_impl(
        profile=profile,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
        },
    )


def _answer_missed_dose_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 복약을 놓쳤을 때는 바로 추가 복용을 단정하기보다, 처방 지시나 약 봉투 안내를 먼저 확인하는 것이 안전합니다.\n"
        "- 다음 복용 시간이 매우 가까우면 임의로 두 번 먹이지 말고\n"
        "- 현재 증상이나 이상 반응이 있으면 의료진이나 약사와 상담해 주세요."
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_emergency_guidance_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 바로 병원이나 119를 생각해야 하는 신호는 다음과 같습니다.\n"
        "- 숨쉬기 힘들어지거나 호흡이 가빠질 때\n"
        "- 입술이 파래지거나 의식이 처지거나 깨우기 어려울 때\n"
        "- 심한 발진, 얼굴 붓기, 전신 두드러기처럼 급격한 이상 반응이 함께 있을 때\n"
        "- 어지러움이 심해져 걷기 어렵거나 쓰러질 것 같을 때"
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_lifestyle_top_intent(
    *,
    guide: Guide | None,
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_lifestyle_top_intent_impl(
        guide=guide,
        profile=profile,
        adherence_summary=adherence_summary,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
            "build_adherence_guidance_points": _build_adherence_guidance_points,
            "compose_medical_sections": _compose_medical_sections,
        },
    )


def _answer_condition_general_intent(
    *,
    condition_name: str | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    profile: PatientProfile | None,
    message: str,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_condition_general_intent_impl(
        condition_name=condition_name,
        meds=meds,
        schedules=schedules,
        profile=profile,
        message=message,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        condition_med_keywords=_CONDITION_MED_KEYWORDS,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
            "dedupe_lines": _dedupe_lines,
            "contains_any": _contains_any,
            "humanize_days": _humanize_days,
            "with_particle": _with_particle,
        },
    )


def _answer_session_summary_intent(
    *,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_session_summary_intent_impl(
        meds=meds,
        profile=profile,
        adherence_summary=adherence_summary,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
            "dedupe_lines": _dedupe_lines,
            "compose_medical_sections": _compose_medical_sections,
        },
    )


def _collect_schedule_lines_for_period(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    period: str,
) -> list[str]:
    med_name_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
    lines: list[str] = []
    for schedule in schedules:
        med = med_name_map.get(int(schedule.get("patient_med_id")), {})
        med_name = str(med.get("display_name") or "").strip()
        dosage = str(med.get("dosage") or "").strip()
        notes = str(med.get("notes") or "").strip()
        if not med_name:
            continue
        if any(keyword in notes for keyword in ["필요", "열날", "증상"]) and period == "night":
            continue
        for item in schedule.get("times") or []:
            time_label = _humanize_time(item.get("time_of_day"))
            hour_raw = str(item.get("time_of_day") or "00:00:00").split(":")[0]
            try:
                hour = int(hour_raw)
            except Exception:
                hour = -1
            if period == "night" and hour < 20:
                continue
            if period == "evening" and not (17 <= hour <= 23):
                continue
            if period == "morning" and not (4 <= hour < 12):
                continue
            label = med_name
            if dosage:
                label += f" {dosage}"
            label += f" ({time_label})"
            lines.append(label)
    return _dedupe_lines(lines, limit=5)


def _answer_tonight_check_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    if not meds and not schedules:
        base = f"{target_label} 기준으로 등록된 복용약이나 복약 일정이 아직 없습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    tonight_lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period="night")
    extra_points: list[str] = []
    for med in meds:
        notes = str(med.get("notes") or "").strip()
        name = str(med.get("display_name") or "").strip()
        if name and any(keyword in notes for keyword in ["필요", "열날", "증상"]):
            extra_points.append(f"{name}은 증상이 있을 때만 복용하는 약인지 함께 확인해 주세요.")
    if tonight_lines:
        base = f"{target_label} 기준 오늘 복약 일정에서 밤에 챙겨야 할 약은 다음과 같습니다.\n" + "\n".join(
            f"- {line}" for line in tonight_lines
        )
        if extra_points:
            base += "\n" + "\n".join(f"- {line}" for line in _dedupe_lines(extra_points, limit=2))
        if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
            recent_missed_names = adherence_summary.get("recent_missed_names") or []
            if recent_missed_names:
                base += "\n- 최근 놓친 기록이 있는 약: " + ", ".join(recent_missed_names[:2])
    else:
        base = f"{target_label} 기준으로 오늘 밤에 해당하는 복약 일정은 현재 뚜렷하게 확인되지 않습니다."
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_schedule_order_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    time_period: str | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    period = time_period or "morning"
    label = {"morning": "아침", "evening": "저녁", "night": "밤"}.get(period, "복약")
    lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period=period)
    if lines:
        base = f"{target_label} 기준으로 {label} 약은 다음 순서로 정리해 볼 수 있습니다.\n" + "\n".join(
            f"- {idx + 1}. {line}" for idx, line in enumerate(lines)
        )
    else:
        base = f"{target_label} 기준으로 {label} 복약 순서를 정리할 일정 정보가 아직 충분하지 않습니다."
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_adherence_priority_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    missed_names = []
    if adherence_summary:
        missed_names = [
            str(name).strip() for name in adherence_summary.get("recent_missed_names") or [] if str(name).strip()
        ]
    if missed_names:
        base = (
            f"{target_label} 기준 최근 복약 기록에서 자주 놓친 약으로는 "
            f"{', '.join(_dedupe_lines(missed_names, limit=3))}이 보입니다.\n"
            "복용 우선순위를 임의로 바꾸기보다, 최근 놓친 약이 오늘 일정에도 있는지 먼저 확인해 빠뜨리지 않는 것이 좋습니다."
        )
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    evening_lines = _collect_schedule_lines_for_period(meds=meds, schedules=schedules, period="evening")
    if evening_lines:
        base = (
            f"{target_label} 기준으로 자주 놓친다면 먼저 챙겨야 할 저녁 약은 다음과 같습니다.\n"
            + "\n".join(f"- {line}" for line in evening_lines[:3])
            + "\n복용 우선순위를 임의로 바꾸기보다, 실제 저녁 일정에 잡힌 약부터 빠뜨리지 않게 확인하는 것이 좋습니다."
        )
    else:
        med_names = [
            str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
        ]
        base = f"{target_label} 기준으로 특정 약 하나를 제일 중요하다고 단정하기보다, 현재 처방된 약을 일정대로 빠뜨리지 않는 것이 더 중요합니다."
        if med_names:
            base += "\n현재 확인되는 약: " + ", ".join(med_names[:4])
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_symptom_cause_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_symptom_cause_intent_impl(
        message=message,
        meds=meds,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "contains_any": _contains_any,
            "dedupe_lines": _dedupe_lines,
        },
    )


def _answer_observation_check_intent(
    *,
    message: str,
    matched_med: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not matched_med:
        return None

    med_name = str(matched_med.get("display_name") or "해당 약").strip()
    normalized = (message or "").strip()
    points: list[str] = []
    if "기침" in normalized or "숨" in normalized or "호흡" in normalized:
        points.append("기침이 더 심해지거나 숨쉬기 힘들어지지 않는지 먼저 확인해 주세요.")
        points.append("말하기 힘들 정도의 호흡곤란, 입술이 파래짐, 처짐이 보이면 즉시 응급진료가 우선입니다.")
    if "열" in normalized:
        points.append("해열제 복용 뒤에도 열이 계속 오르거나 처짐이 심해지는지 함께 보세요.")
    if "발진" in normalized or "두드러기" in normalized:
        points.append("발진, 얼굴 붓기, 전신 두드러기가 생기면 추가 복용 전에 바로 상태를 확인해야 합니다.")

    if not points:
        points.append("복용 뒤 증상이 더 심해지지 않는지와 새로 생긴 이상 반응이 없는지를 먼저 확인해 주세요.")

    base = f"{target_label} 기준으로 {med_name} 복용 뒤에는 다음 상태를 먼저 보면 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=3)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_school_observation_intent(
    *,
    profile: PatientProfile | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    points: list[str] = []
    if any("천식" in item for item in conditions):
        points.append("기침이 평소보다 심해지거나 숨쉬기 힘들어하는지 봐 달라고 전해 주세요.")
        points.append(
            "말을 하기 힘들 정도로 숨이 차거나 처지는 모습이 보이면 바로 보호자에게 연락해 달라고 하는 것이 좋습니다."
        )
    if any("비염" in item for item in conditions):
        points.append("콧물, 코막힘이 심해지면서 수업에 집중하기 어려워하는지도 함께 봐 달라고 할 수 있습니다.")
    if not points:
        points.append("복용 뒤 졸림, 발진, 호흡 불편 같은 새로운 증상이 없는지 봐 달라고 전하는 것이 좋습니다.")
    base = f"{target_label} 기준으로 학교에서는 다음 증상을 특히 봐 달라고 전달하면 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=3)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_cold_med_caution_intent(
    *,
    profile: PatientProfile | None,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    points: list[str] = []
    allergies = _split_text_items(getattr(profile, "allergies", None) if profile else None)
    conditions = _split_text_items(getattr(profile, "conditions", None) if profile else None)
    if allergies:
        points.append("알레르기 성분이 겹치지 않는지 먼저 성분표를 확인하는 것이 좋습니다.")
    if any("고혈압" in item for item in conditions):
        points.append("코감기약 성분 중 혈압을 올릴 수 있는 성분은 없는지 확인하는 것이 좋습니다.")
    if any("골다공증" in item for item in conditions):
        points.append("골다공증 약 복용 시간과 겹치지 않게 공복약/식후약 순서를 함께 확인하세요.")
    if any("고지혈증" in item for item in conditions):
        points.append("현재 복용 중인 지질강하제와 함께 먹어도 되는지 약사나 의료진에게 확인하는 것이 안전합니다.")
    if meds:
        med_names = [
            str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
        ]
        if med_names:
            points.append("현재 복용약: " + ", ".join(med_names[:4]))

    base = f"{target_label} 기준으로 감기약을 새로 먹게 되면 다음 점을 먼저 확인하는 것이 좋습니다.\n" + "\n".join(
        f"- {item}" for item in _dedupe_lines(points, limit=4)
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_rash_intent(
    *,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    base = (
        f"{target_label} 기준으로 약 복용 후 두드러기나 발진이 생기면 추가 복용 전에 상태를 먼저 확인하는 것이 안전합니다.\n"
        "- 숨쉬기 힘듦, 얼굴 붓기, 전신 두드러기가 함께 있으면 즉시 응급진료가 우선이고\n"
        "- 가벼운 피부 발진이라도 복용 약 이름과 발생 시간을 기록해 의료진과 상담해 주세요."
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


# 스케줄 기반 직접 응답
def _answer_schedule_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    schedule_text = _build_schedule_text(schedules, meds)
    if schedule_text == "등록된 복약 일정 없음":
        base = f"{target_label} 기준으로 등록된 복약 일정이 없습니다."
    else:
        base = f"{target_label} 기준 복약 일정은 다음과 같습니다.\n{schedule_text}"

    if audience == "senior":
        base += "\n어지러움이나 복약 시간 혼동이 생기지 않도록 복용 전 다시 확인하는 것이 좋습니다."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _answer_hospital_schedule_intent(
    *,
    hospital_schedules: list[HospitalSchedule],
    message: str,
    session_memory: ChatSessionMemory | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _answer_hospital_schedule_intent_impl(
        hospital_schedules=hospital_schedules,
        message=message,
        session_memory=session_memory,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "contains_any": _contains_any,
            "affirmative_short_replies": _AFFIRMATIVE_SHORT_REPLIES,
            "format_datetime_korean": _format_datetime_korean,
            "build_hospital_schedule_text": _build_hospital_schedule_text,
        },
    )


def _med_category_flags(name: str) -> set[str]:
    normalized = _compact_text(name).lower()
    flags: set[str] = set()
    if any(token in normalized for token in ["아세트아미노펜", "타이레놀", "게보린"]):
        flags.add("acetaminophen")
    if any(token in normalized for token in ["탁센", "이부프로펜", "나프록센", "덱시", "록소", "아스피린"]):
        flags.add("nsaid")
    if any(token in normalized for token in ["비염", "항히스타민", "세티리진", "로라타딘", "펙소"]):
        flags.add("antihistamine")
    return flags


def _build_interaction_focus_points(
    *, med_names: list[str], adherence_summary: dict[str, Any] | None
) -> tuple[list[str], list[str], list[str]]:
    return _build_interaction_focus_points_impl(
        med_names=med_names,
        adherence_summary=adherence_summary,
        ops={
            "dedupe_lines": _dedupe_lines,
            "med_category_flags": _med_category_flags,
        },
    )


def _build_external_interaction_points(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    lookup: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    return _build_external_interaction_points_impl(
        external_drug_name=external_drug_name,
        meds=meds,
        profile=profile,
        adherence_summary=adherence_summary,
        lookup=lookup,
        ops={
            "dedupe_lines": _dedupe_lines,
            "med_category_flags": _med_category_flags,
            "split_text_items": _split_text_items,
            "summarize_text": _summarize_text,
        },
    )


def _answer_drug_interaction_overview(
    *,
    meds: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    med_names = [
        str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
    ]
    if len(med_names) < 2:
        base = f"{target_label} 기준으로 비교할 복용약 정보가 아직 충분하지 않습니다."
        return (
            _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base
        )

    record_points, general_points, next_points = _build_interaction_focus_points(
        med_names=med_names,
        adherence_summary=adherence_summary,
    )
    base = _compose_medical_sections(
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


def _build_clarification_reply(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return _build_clarification_reply_impl(
        analysis=analysis,
        context=context,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "normalize_user_message": _normalize_user_message,
            "contains_any": _contains_any,
            "followup_med_references": _FOLLOWUP_MED_REFERENCES,
            "answer_hospital_schedule_intent": _answer_hospital_schedule_intent,
            "answer_drug_interaction_overview": _answer_drug_interaction_overview,
        },
    )


async def _render_planned_reply(
    *,
    plan: ChatPlan | None,
    message: str,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return await _render_planned_reply_impl(
        plan=plan,
        message=message,
        context=context,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        plan_factory=ChatPlan,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "compose_answers": _compose_answers,
            "extract_target_med": _extract_target_med,
            "answer_profile_intent": _answer_profile_intent,
            "answer_profile_guidance_intent": _answer_profile_guidance_intent,
            "answer_condition_general_intent": _answer_condition_general_intent,
            "answer_hospital_schedule_intent": _answer_hospital_schedule_intent,
            "answer_med_detail_intent": _answer_med_detail_intent,
            "answer_med_list_intent": _answer_med_list_intent,
            "answer_schedule_intent": _answer_schedule_intent,
            "answer_external_med_intent": _answer_external_med_intent,
            "answer_external_interaction_intent": _answer_external_interaction_intent,
            "answer_drug_interaction_overview": _answer_drug_interaction_overview,
        },
    )


# guide 기반 직접 응답
def _answer_guide_intent(
    *,
    guide: Guide | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    if not guide or not guide.content_text:
        return None

    base = f"{target_label} 기준 최신 가이드를 요약하면 다음과 같습니다.\n{guide.content_text}"

    if audience == "child":
        base += "\n어려운 부분은 보호자와 같이 확인하면 좋습니다."
    elif audience == "senior":
        base += "\n어지러움이나 낙상 위험이 있으면 복용 후 상태를 더 주의 깊게 살펴주세요."

    return _to_caregiver_style(answer=base, audience=audience) if requester_role == RequesterRole.CAREGIVER else base


async def _answer_medication_caution_intent(
    *,
    message: str,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    dur_alerts: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    recent_messages: list[ChatMessage] | None,
    matched_med: dict[str, Any] | None = None,
    external_drug_name: str | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return await _answer_medication_caution_intent_impl(
        message=message,
        guide=guide,
        meds=meds,
        profile=profile,
        dur_alerts=dur_alerts,
        adherence_summary=adherence_summary,
        recent_messages=recent_messages,
        matched_med=matched_med,
        external_drug_name=external_drug_name,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "contains_any": _contains_any,
            "extract_external_drug_name": _extract_external_drug_name,
            "answer_external_interaction_intent": _answer_external_interaction_intent,
            "build_interaction_focus_points": _build_interaction_focus_points,
            "compose_medical_sections": _compose_medical_sections,
            "extract_target_med": _extract_target_med,
            "lookup_external_med_info": _lookup_external_med_info,
            "first_clean_line": _first_clean_line,
            "extract_dur_alert_points": _extract_dur_alert_points,
        },
    )


def _answer_general_caution_intent(
    *,
    profile: PatientProfile | None,
    guide: Guide | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    return _answer_general_caution_intent_impl(
        profile=profile,
        guide=guide,
        meds=meds,
        schedules=schedules,
        adherence_summary=adherence_summary,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
            "build_schedule_text": _build_schedule_text,
            "first_clean_line": _first_clean_line,
            "build_adherence_guidance_points": _build_adherence_guidance_points,
            "dedupe_lines": _dedupe_lines,
        },
    )


async def _answer_external_med_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[ChatMessage] | None,
    profile: PatientProfile | None,
    external_drug_name: str | None = None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return await _answer_external_med_intent_impl(
        message=message,
        meds=meds,
        schedules=schedules,
        recent_messages=recent_messages,
        profile=profile,
        external_drug_name=external_drug_name,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "extract_external_drug_name": _extract_external_drug_name,
            "find_best_med_match": _find_best_med_match,
            "answer_med_detail_intent": _answer_med_detail_intent,
            "choose_korean_particle": _choose_korean_particle,
            "lookup_external_med_info": _lookup_external_med_info,
            "split_text_items": _split_text_items,
            "summarize_text": _summarize_text,
            "compose_medical_sections": _compose_medical_sections,
        },
    )


async def _answer_external_interaction_intent(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return await _answer_external_interaction_intent_impl(
        external_drug_name=external_drug_name,
        meds=meds,
        profile=profile,
        adherence_summary=adherence_summary,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "lookup_external_med_info": _lookup_external_med_info,
            "build_external_interaction_points": _build_external_interaction_points,
            "compose_medical_sections": _compose_medical_sections,
        },
    )


# 일상 대화 응답
def _answer_daily_chat(
    *,
    message: str,
    requester_role: RequesterRole,
    target_label: str,
    data_readiness: str = "partial",
) -> str:
    return _answer_daily_chat_impl(
        message=message,
        requester_role=requester_role,
        target_label=target_label,
        data_readiness=data_readiness,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "contains_any": _contains_any,
            "bot_capability_keywords": _BOT_CAPABILITY_KEYWORDS,
        },
    )


def _extract_core_answer(answer: str, requester_role: RequesterRole) -> str:
    text = str(answer or "").replace(CHAT_DISCLAIMER, "").strip()
    return text


def _compose_answers(
    *,
    answers: list[str],
    requester_role: RequesterRole,
    audience: str,
) -> str | None:
    parts: list[str] = []
    seen: set[str] = set()
    for answer in answers:
        core = _extract_core_answer(answer, requester_role)
        if core and core not in seen:
            seen.add(core)
            parts.append(core)

    if not parts:
        return None

    combined = "\n\n".join(parts[:3])
    combined = re.sub(r"(회원님 기록 기준으로|선택한 복약자 기준으로)\s*", "", combined)
    combined = combined.strip()
    if requester_role == RequesterRole.CAREGIVER:
        return _to_caregiver_style(answer=combined, audience=audience)
    return combined


def _compose_medical_sections(
    *,
    current_record_points: list[str],
    general_info_points: list[str],
    next_check_points: list[str],
) -> str:
    sections: list[str] = []

    current_points = _dedupe_lines(current_record_points, limit=4)
    general_points = _dedupe_lines(general_info_points, limit=3)
    next_points = _dedupe_lines(next_check_points, limit=3)

    if current_points:
        sections.append("현재 기록 기준\n" + "\n".join(f"- {item}" for item in current_points))
    if general_points:
        sections.append("일반적으로 보면\n" + "\n".join(f"- {item}" for item in general_points))
    if next_points:
        sections.append("지금 확인할 포인트\n" + "\n".join(f"- {item}" for item in next_points))

    return "\n\n".join(sections).strip()


def _should_finalize_with_rules(
    *,
    analysis: QuestionAnalysis,
    composed_answer: str | None,
    clarification_reply: str | None,
) -> bool:
    if clarification_reply:
        return True
    if not composed_answer:
        return False
    if analysis.answer_mode in {"daily_chat", "direct_fact", "safety_guidance", "external_drug_counseling"}:
        return True
    if analysis.primary_intent in {
        "daily",
        "external_med",
        "condition_general",
        "medication_caution",
        "med_detail",
        "med_list",
        "schedule",
        "hospital_schedule",
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "general_caution",
        "tonight_check",
        "adherence_priority",
        "session_summary",
        "lifestyle_top",
    }:
        return True
    return False


def _build_fact_summary(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
) -> str:
    return _build_fact_summary_impl(
        analysis=analysis,
        context=context,
        target_label=target_label,
        ops={
            "humanize_days": _humanize_days,
            "humanize_time": _humanize_time,
            "format_datetime_korean": _format_datetime_korean,
            "extract_dur_alert_points": _extract_dur_alert_points,
            "build_med_adherence_points": _build_med_adherence_points,
            "build_adherence_guidance_points": _build_adherence_guidance_points,
            "contains_keyword": _contains_keyword,
            "split_text_items": _split_text_items,
            "first_clean_line": _first_clean_line,
            "dedupe_lines": _dedupe_lines,
        },
    )


def _normalize_intent_order(intents: list[str], requester_role: RequesterRole) -> list[str]:
    return _normalize_intent_order_impl(intents=intents, requester_role=requester_role, caregiver_role=RequesterRole.CAREGIVER)


# LLM 호출
async def _call_chat_model(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    try:
        import httpx
    except Exception as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError("httpx package is required for LLM calls") from exc

    return await _call_chat_model_impl(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        ops={
            "getenv": os.getenv,
            "perf_counter": perf_counter,
            "httpx_client": httpx.AsyncClient,
            "log_metric": _log_chat_metric,
            "chat_disclaimer": CHAT_DISCLAIMER,
        },
    )


async def _plan_chat_question(
    *,
    message: str,
    context: PatientChatContext,
    requester_role: RequesterRole,
    audience: str,
    target_label: str,
) -> ChatPlan | None:
    return await _plan_chat_question_impl(
        message=message,
        context=context,
        requester_role=requester_role,
        audience=audience,
        target_label=target_label,
        plan_factory=ChatPlan,
        ops={
            "logger": logger,
            "has_openai_api_key": _has_openai_api_key,
            "read_prompt_template": _read_prompt_template,
            "audience_label": _audience_label,
            "build_meds_text": _build_meds_text,
            "build_schedule_text": _build_schedule_text,
            "build_hospital_schedule_brief": _build_hospital_schedule_brief,
            "build_profile_text": _build_profile_text,
            "build_recent_history_for_planner": _build_recent_history_for_planner,
            "build_session_memory_text": _build_session_memory_text,
            "call_chat_model": _call_chat_model,
        },
    )


# 일반 fallback 답변
def _fallback_reply(
    *,
    intent: str,
    latest_guide: Guide | None,
    meds: list[dict[str, Any]],
    profile: PatientProfile | None,
    meds_text: str,
    schedule_text: str,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> str:
    return _fallback_reply_impl(
        intent=intent,
        latest_guide=latest_guide,
        meds=meds,
        profile=profile,
        schedule_text=schedule_text,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "caregiver_role": RequesterRole.CAREGIVER,
            "to_caregiver_style": _to_caregiver_style,
            "split_text_items": _split_text_items,
        },
    )


# assistant 응급 플래그 재구성
def _reconstruct_emergency_fields(*, current: ChatMessage, previous: ChatMessage | None) -> tuple[bool, str | None]:
    if current.role != "assistant":
        return False, None

    if previous and previous.role == "user":
        is_emergency, emergency_message = _detect_emergency(previous.content)
        if is_emergency:
            return True, emergency_message

    if "응급 상황이 의심됩니다" in current.content:
        return True, "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실/의료기관에 연락해 주세요."

    return False, None


async def _build_deterministic_answer_parts(
    *,
    analysis: QuestionAnalysis,
    context: PatientChatContext,
    target_label: str,
    requester_role: RequesterRole,
    audience: str,
) -> list[str]:
    return await _build_deterministic_answer_parts_impl(
        analysis=analysis,
        context=context,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
        ops={
            "resolve_data_readiness": _resolve_data_readiness,
            "answer_profile_guidance_intent": _answer_profile_guidance_intent,
            "answer_profile_intent": _answer_profile_intent,
            "answer_med_time_split_intent": _answer_med_time_split_intent,
            "answer_med_regularity_intent": _answer_med_regularity_intent,
            "answer_med_prn_intent": _answer_med_prn_intent,
            "answer_med_detail_intent": _answer_med_detail_intent,
            "answer_med_list_intent": _answer_med_list_intent,
            "answer_caregiver_check_intent": _answer_caregiver_check_intent,
            "answer_self_check_intent": _answer_self_check_intent,
            "answer_allergy_food_intent": _answer_allergy_food_intent,
            "answer_missed_dose_intent": _answer_missed_dose_intent,
            "answer_emergency_guidance_intent": _answer_emergency_guidance_intent,
            "answer_lifestyle_top_intent": _answer_lifestyle_top_intent,
            "answer_session_summary_intent": _answer_session_summary_intent,
            "answer_tonight_check_intent": _answer_tonight_check_intent,
            "answer_schedule_order_intent": _answer_schedule_order_intent,
            "answer_adherence_priority_intent": _answer_adherence_priority_intent,
            "answer_symptom_cause_intent": _answer_symptom_cause_intent,
            "answer_observation_check_intent": _answer_observation_check_intent,
            "answer_school_observation_intent": _answer_school_observation_intent,
            "answer_cold_med_caution_intent": _answer_cold_med_caution_intent,
            "answer_rash_intent": _answer_rash_intent,
            "answer_schedule_intent": _answer_schedule_intent,
            "answer_hospital_schedule_intent": _answer_hospital_schedule_intent,
            "answer_medication_caution_intent": _answer_medication_caution_intent,
            "answer_general_caution_intent": _answer_general_caution_intent,
            "answer_external_med_intent": _answer_external_med_intent,
            "answer_condition_general_intent": _answer_condition_general_intent,
            "answer_guide_intent": _answer_guide_intent,
            "answer_daily_chat": _answer_daily_chat,
        },
    )


class ChatService:
    @staticmethod
    def _to_chat_message_item(*, row: ChatMessage, previous: ChatMessage | None = None) -> ChatMessageItem:
        is_emergency, emergency_message = _reconstruct_emergency_fields(
            current=row,
            previous=previous,
        )
        return ChatMessageItem(
            message_id=int(row.id),
            role=row.role,
            content=row.content,
            status=str(getattr(row, "status", "") or "completed"),
            error_message=getattr(row, "error_message", None),
            is_emergency=is_emergency,
            emergency_message=emergency_message,
            disclaimer=CHAT_DISCLAIMER if row.role == "assistant" else None,
            created_at=row.created_at,
        )

    @staticmethod
    async def _enqueue_chat_reply_task(*, session_id: int, user_message_id: int, assistant_message_id: int) -> None:
        payload = {
            "task": "generate_chat_reply",
            "session_id": session_id,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
        }
        client = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.lpush(CHAT_WORKER_QUEUE, json.dumps(payload, ensure_ascii=False))
        finally:
            await client.aclose()

    @staticmethod
    async def _generate_assistant_content(
        *,
        session_id: int,
        patient_id: int,
        requester: User,
        stripped: str,
    ) -> tuple[str, QuestionAnalysis, ChatPlan | None, PatientChatContext]:
        requester_role = await _resolve_requester_role(int(requester.id))
        target_label = "선택한 복약자" if requester_role == RequesterRole.CAREGIVER else "회원님 기록"

        context = await _build_patient_chat_context(
            session_id=session_id,
            patient_id=patient_id,
            include_kids_evidence=False,
        )

        audience = _resolve_audience(context.profile)
        chat_plan = await _plan_chat_question(
            message=stripped,
            context=context,
            requester_role=requester_role,
            audience=audience,
            target_label=target_label,
        )
        analysis = _analyze_question(
            message=stripped,
            meds=context.meds,
            recent_messages=context.recent_messages,
            requester_role=requester_role,
            profile=context.profile,
            session_memory=context.session_memory,
        )
        chat_plan = _harmonize_chat_plan(analysis=analysis, plan=chat_plan)
        is_emergency = analysis.is_emergency
        emergency_message = analysis.emergency_message
        intent = analysis.primary_intent
        llm_preferred = _should_prefer_llm(analysis=analysis)
        record_context_available = _has_required_context_for_request(
            analysis=analysis,
            plan=chat_plan,
            context=context,
        )
        personalized_request = _is_personalized_request(analysis=analysis, plan=chat_plan)

        if analysis.primary_intent in EXTERNAL_EVIDENCE_INTENTS:
            context.kids_evidence = await _build_kids_evidence(meds=context.meds)

        context.rag_context = await _build_rag_context(
            intent=intent,
            latest_guide=context.latest_guide,
            meds=context.meds,
            schedules=context.schedules,
            profile=context.profile,
            kids_evidence=context.kids_evidence,
        )

        if is_emergency:
            assistant_content = f"{emergency_message} 현재 질문은 즉시 전문 의료진 확인이 우선입니다."
            return assistant_content, analysis, chat_plan, context

        if personalized_request and not record_context_available:
            assistant_content = _build_record_required_reply(
                analysis=analysis,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
            return assistant_content, analysis, chat_plan, context

        planned_reply = await _render_planned_reply(
            plan=chat_plan,
            message=stripped,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        if planned_reply:
            return planned_reply, analysis, chat_plan, context

        deterministic_parts = await _build_deterministic_answer_parts(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

        composed_answer = _compose_answers(
            answers=deterministic_parts,
            requester_role=requester_role,
            audience=audience,
        )

        meds_text = _build_meds_text(context.meds)
        schedule_text = _build_schedule_text(context.schedules, context.meds)
        hospital_schedule_text = _build_hospital_schedule_text(context.hospital_schedules)
        profile_text = _build_profile_text(context.profile)
        guide_text = _build_guide_text(context.latest_guide)
        history_text = _build_history_text(context.recent_messages)
        session_memory_text = _build_session_memory_text(context.session_memory)
        kids_text = _build_kids_text(context.kids_evidence)
        rag_text = _build_rag_text(context.rag_context)
        deterministic_text = _build_fact_summary(
            analysis=analysis,
            context=context,
            target_label=target_label,
        )
        if composed_answer:
            deterministic_text = (
                deterministic_text + "\n- 현재 직접 답변 초안: " + _extract_core_answer(composed_answer, requester_role)
            )
        external_lookup = (
            await _lookup_external_med_info(analysis.external_drug_name) if analysis.external_drug_name else None
        )
        external_drug_text = _build_external_drug_text(
            drug_name=analysis.external_drug_name,
            lookup=external_lookup,
        )
        clarification_reply = _build_clarification_reply(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

        if clarification_reply:
            return clarification_reply, analysis, chat_plan, context

        if _should_finalize_with_rules(
            analysis=analysis,
            composed_answer=composed_answer,
            clarification_reply=clarification_reply,
        ):
            assistant_content = composed_answer or _fallback_reply(
                intent=intent,
                latest_guide=context.latest_guide,
                meds=context.meds,
                profile=context.profile,
                meds_text=meds_text,
                schedule_text=schedule_text,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
            return assistant_content, analysis, chat_plan, context

        if llm_preferred:
            try:
                system_prompt = _read_prompt_template("chat_system_prompt.txt").format(
                    requester_role=requester_role.value,
                    target_label=target_label,
                    answer_mode=analysis.answer_mode,
                    audience_label=_audience_label(audience),
                    extra_safety=_extra_safety_text(audience),
                    kids_text=kids_text,
                    rag_text=rag_text,
                    external_drug_text=external_drug_text,
                    deterministic_text=deterministic_text,
                    disclaimer=CHAT_DISCLAIMER,
                )
                user_prompt = _read_prompt_template("chat_user_prompt.txt").format(
                    guide_text=guide_text,
                    meds_text=meds_text,
                    schedule_text=schedule_text,
                    hospital_schedule_text=hospital_schedule_text,
                    profile_text=profile_text,
                    external_drug_text=external_drug_text,
                    deterministic_text=deterministic_text,
                    history_text=history_text,
                    session_memory_text=session_memory_text,
                    user_message=stripped,
                )
                llm_result = await _call_chat_model(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
                assistant_content = (llm_result.get("content") or "").strip()
                if not assistant_content:
                    raise ValueError("empty assistant content")
                return assistant_content, analysis, chat_plan, context
            except Exception:
                logger.exception("chat fallback used session_id=%s", session_id)

        assistant_content = composed_answer or _fallback_reply(
            intent=intent,
            latest_guide=context.latest_guide,
            meds=context.meds,
            profile=context.profile,
            meds_text=meds_text,
            schedule_text=schedule_text,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        return assistant_content, analysis, chat_plan, context

    @staticmethod
    async def _generate_fast_assistant_content(
        *,
        session_id: int,
        patient_id: int,
        requester: User,
        stripped: str,
    ) -> tuple[str, QuestionAnalysis, PatientChatContext] | None:
        requester_role = await _resolve_requester_role(int(requester.id))
        context = await _build_patient_chat_context(
            session_id=session_id,
            patient_id=patient_id,
            include_kids_evidence=False,
        )
        analysis = _analyze_question(
            message=stripped,
            meds=context.meds,
            recent_messages=context.recent_messages,
            requester_role=requester_role,
            profile=context.profile,
            session_memory=context.session_memory,
        )
        if analysis.primary_intent not in FAST_SYNC_INTENTS:
            return None

        target_label = "선택한 복약자" if requester_role == RequesterRole.CAREGIVER else "회원님 기록"
        audience = _resolve_audience(context.profile)
        answers = await _build_deterministic_answer_parts(
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        assistant_content = _compose_answers(
            answers=answers,
            requester_role=requester_role,
            audience=audience,
        )
        if not assistant_content:
            return None
        return assistant_content, analysis, context

    @staticmethod
    async def create_session(
        *,
        requester: User,
        patient_id: int,
        mode: str,
    ) -> ChatSessionCreateResponse:
        session = await ChatSession.create(
            user_id=int(requester.id),
            patient_id=patient_id,
            mode=mode,
        )
        await ChatSessionMemory.get_or_create(session_id=int(session.id))

        return ChatSessionCreateResponse(
            success=True,
            data=ChatSessionCreateData(
                session_id=int(session.id),
                patient_id=patient_id,
                mode=mode,
                created_at=session.created_at,
            ),
        )

    @staticmethod
    async def create_feedback(
        *,
        requester: User,
        session_id: int,
        assistant_message_id: int,
        helpful: bool,
        feedback_type: str | None,
        comment: str | None,
    ) -> ChatFeedbackCreateResponse:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        assistant_message = await ChatMessage.get_or_none(
            id=assistant_message_id,
            session_id=session_id,
            role="assistant",
        )
        if not assistant_message:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_MESSAGE_NOT_FOUND",
                message="피드백 대상 assistant 메시지를 찾을 수 없습니다.",
            )

        feedback = await ChatFeedback.create(
            session_id=session_id,
            assistant_message_id=assistant_message_id,
            user_id=int(requester.id),
            helpful=helpful,
            feedback_type=str(feedback_type or "").strip()[:50] or None,
            comment=str(comment or "").strip()[:1000] or None,
        )

        return ChatFeedbackCreateResponse(
            success=True,
            data=ChatFeedbackCreateData(
                feedback_id=int(feedback.id),
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                helpful=feedback.helpful,
                feedback_type=feedback.feedback_type,
                comment=feedback.comment,
                created_at=feedback.created_at,
            ),
        )

    @staticmethod
    async def list_messages(*, session_id: int) -> ChatMessageListResponse:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        rows = await ChatMessage.filter(session_id=session_id).order_by("created_at", "id").all()

        items: list[ChatMessageItem] = []
        for idx, row in enumerate(rows):
            prev_row = rows[idx - 1] if idx > 0 else None
            items.append(ChatService._to_chat_message_item(row=row, previous=prev_row))

        return ChatMessageListResponse(
            success=True,
            data=ChatMessageListData(
                session_id=int(session.id),
                items=items,
                total=len(items),
            ),
        )

    @staticmethod
    async def create_message(
        *,
        requester: User,
        session_id: int,
        content: str,
    ) -> ChatMessageCreateResponse:
        started = perf_counter()
        stripped = _normalize_user_message(content)
        if not stripped:
            raise ChatServiceError(
                status_code=422,
                code="MESSAGE_EMPTY",
                message="메시지를 입력해 주세요.",
            )
        if len(stripped) > CHAT_MAX_MESSAGE_CHARS:
            raise ChatServiceError(
                status_code=422,
                code="MESSAGE_TOO_LONG",
                message=f"메시지는 {CHAT_MAX_MESSAGE_CHARS}자 이하로 입력해 주세요.",
            )

        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        patient_id = getattr(session, "patient_id", None)
        if patient_id is None:
            raise ChatServiceError(
                status_code=500,
                code="CHAT_SESSION_PATIENT_MISSING",
                message="세션에 연결된 환자 정보가 없습니다.",
            )

        user_msg = await ChatMessage.create(
            session_id=session_id,
            role="user",
            content=stripped,
            status="completed",
            completed_at=datetime.now(),
        )

        fast_result = await ChatService._generate_fast_assistant_content(
            session_id=int(session.id),
            patient_id=int(patient_id),
            requester=requester,
            stripped=stripped,
        )
        if fast_result:
            assistant_content, analysis, context = fast_result
            assistant_content = _apply_response_contract(content=assistant_content, analysis=analysis)
            assistant_msg = await ChatMessage.create(
                session_id=session_id,
                role="assistant",
                content=assistant_content,
                status="completed",
                completed_at=datetime.now(),
            )
            await _update_session_memory(
                session_id=int(session.id),
                analysis=analysis,
                plan=None,
                assistant_content=assistant_content,
                context=context,
            )
            _log_chat_metric(
                "create_message_fast",
                session_id=session_id,
                intent=analysis.primary_intent,
                elapsed_ms=int((perf_counter() - started) * 1000),
            )
            return ChatMessageCreateResponse(
                success=True,
                data=ChatMessageCreateData(
                    session_id=int(session.id),
                    user_message=ChatService._to_chat_message_item(row=user_msg),
                    assistant_message=ChatService._to_chat_message_item(row=assistant_msg, previous=user_msg),
                ),
            )

        assistant_msg = await ChatMessage.create(
            session_id=session_id,
            role="assistant",
            content="응답을 준비하고 있습니다.",
            status="queued",
        )

        await ChatService._enqueue_chat_reply_task(
            session_id=int(session.id),
            user_message_id=int(user_msg.id),
            assistant_message_id=int(assistant_msg.id),
        )
        _log_chat_metric(
            "create_message_queued",
            session_id=session_id,
            elapsed_ms=int((perf_counter() - started) * 1000),
        )

        return ChatMessageCreateResponse(
            success=True,
            data=ChatMessageCreateData(
                session_id=int(session.id),
                user_message=ChatService._to_chat_message_item(row=user_msg),
                assistant_message=ChatService._to_chat_message_item(row=assistant_msg, previous=user_msg),
            ),
        )

    @staticmethod
    async def generate_assistant_reply(
        *,
        session_id: int,
        user_message_id: int,
        assistant_message_id: int,
    ) -> None:
        started_monotonic = datetime.now()
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_SESSION_NOT_FOUND",
                message="채팅 세션을 찾을 수 없습니다.",
            )

        patient_id = getattr(session, "patient_id", None)
        if patient_id is None:
            raise ChatServiceError(
                status_code=500,
                code="CHAT_SESSION_PATIENT_MISSING",
                message="세션에 연결된 환자 정보가 없습니다.",
            )

        user_msg = await ChatMessage.get_or_none(
            id=user_message_id,
            session_id=session_id,
            role="user",
        )
        assistant_msg = await ChatMessage.get_or_none(
            id=assistant_message_id,
            session_id=session_id,
            role="assistant",
        )
        if not user_msg or not assistant_msg:
            raise ChatServiceError(
                status_code=404,
                code="CHAT_MESSAGE_NOT_FOUND",
                message="채팅 메시지를 찾을 수 없습니다.",
            )

        assistant_status = str(getattr(assistant_msg, "status", "") or "")
        if (
            assistant_status == "completed"
            and assistant_msg.content
            and assistant_msg.content != "응답을 준비하고 있습니다."
        ):
            return

        assistant_msg.status = "processing"
        assistant_msg.error_message = None
        assistant_msg.started_at = datetime.now()
        await assistant_msg.save(update_fields=["status", "error_message", "started_at"])

        try:
            requester = await User.get(id=int(session.user_id))
            assistant_content, analysis, chat_plan, context = await ChatService._generate_assistant_content(
                session_id=session_id,
                patient_id=int(patient_id),
                requester=requester,
                stripped=_normalize_user_message(user_msg.content),
            )
            assistant_content = _apply_response_contract(content=assistant_content, analysis=analysis)

            assistant_msg.content = assistant_content
            assistant_msg.status = "completed"
            assistant_msg.error_message = None
            assistant_msg.completed_at = datetime.now()
            await assistant_msg.save(update_fields=["content", "status", "error_message", "completed_at"])

            await _update_session_memory(
                session_id=session_id,
                analysis=analysis,
                plan=chat_plan,
                assistant_content=assistant_content,
                context=context,
            )
            elapsed = (datetime.now() - started_monotonic).total_seconds()
            if elapsed >= CHAT_SLOW_REPLY_SECONDS:
                logger.warning(
                    "chat slow reply session_id=%s assistant_message_id=%s intent=%s elapsed=%.2fs",
                    session_id,
                    assistant_message_id,
                    analysis.primary_intent,
                    elapsed,
                )
            else:
                logger.info(
                    "chat reply completed session_id=%s assistant_message_id=%s intent=%s elapsed=%.2fs",
                    session_id,
                    assistant_message_id,
                    analysis.primary_intent,
                    elapsed,
                )
            _log_chat_metric(
                "reply_completed",
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                intent=analysis.primary_intent,
                answer_mode=analysis.answer_mode,
                elapsed_ms=int(elapsed * 1000),
            )
        except Exception as exc:
            logger.exception(
                "chat async reply failed session_id=%s assistant_message_id=%s", session_id, assistant_message_id
            )
            assistant_msg.content = "일시적인 오류로 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."
            assistant_msg.status = "failed"
            assistant_msg.error_message = str(exc)[:1000]
            assistant_msg.completed_at = datetime.now()
            await assistant_msg.save(update_fields=["content", "status", "error_message", "completed_at"])
            _log_chat_metric(
                "reply_failed",
                session_id=session_id,
                assistant_message_id=assistant_message_id,
                error_type=type(exc).__name__,
            )
