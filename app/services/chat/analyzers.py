from __future__ import annotations

from typing import Any

from app.services.chat.keywords import (
    _AFFIRMATIVE_SHORT_REPLIES,
    _BOT_CAPABILITY_KEYWORDS,
    _CLARIFICATION_RESET_PREFIXES,
    _DAILY_CHAT_KEYWORDS,
    _GUIDE_SUMMARY_KEYWORDS,
    _HOSPITAL_SCHEDULE_KEYWORDS,
    _MEDICATION_CAUTION_KEYWORDS,
    _PROFILE_ALCOHOL_KEYWORDS,
    _PROFILE_ALLERGY_KEYWORDS,
    _PROFILE_BODY_KEYWORDS,
    _PROFILE_CONDITION_KEYWORDS,
    _PROFILE_EXERCISE_KEYWORDS,
    _PROFILE_HOSPITALIZATION_KEYWORDS,
    _PROFILE_SLEEP_KEYWORDS,
    _PROFILE_SMOKING_KEYWORDS,
    _PROFILE_SUMMARY_KEYWORDS,
    _SYMPTOM_WORDS,
)
from app.services.chat.quality import normalize_user_message
from app.services.chat.text_utils import contains_any, contains_keyword, split_text_items

_PROFILE_RELATED_KEYWORDS = (
    _PROFILE_SMOKING_KEYWORDS
    + _PROFILE_ALCOHOL_KEYWORDS
    + _PROFILE_SLEEP_KEYWORDS
    + _PROFILE_EXERCISE_KEYWORDS
    + _PROFILE_CONDITION_KEYWORDS
    + _PROFILE_ALLERGY_KEYWORDS
    + _PROFILE_HOSPITALIZATION_KEYWORDS
)
_CLARIFICATION_RESET_EXCLUDE_KEYWORDS = _MEDICATION_CAUTION_KEYWORDS + [
    "같이 먹",
    "함께 먹",
    "추가로 먹",
    "먹어도 돼",
    "복용해도 돼",
    "상호작용",
    "조합",
]


def resolve_answer_mode(*, intents: list[str], is_emergency: bool) -> str:
    if is_emergency:
        return "emergency"
    if "external_med" in intents:
        return "external_drug_counseling"
    if "condition_general" in intents:
        return "condition_counseling"
    if "daily" in intents:
        return "daily_chat"
    if any(intent in intents for intent in {"missed_dose", "emergency_guidance", "rash"}):
        return "safety_guidance"
    if len(intents) == 1 and intents[0] in {
        "profile_body",
        "profile_summary",
        "profile_guidance",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
        "profile_hospitalization",
        "med_list",
        "med_time_split",
        "med_regularity",
        "schedule",
        "session_summary",
        "tonight_check",
        "schedule_order",
        "adherence_priority",
        "symptom_cause",
        "observation_check",
        "school_observation",
        "cold_med_caution",
        "hospital_schedule",
    }:
        return "direct_fact"
    if any(
        intent in intents
        for intent in {"caregiver_check", "self_check", "lifestyle_top", "general_caution", "guide", "profile_guidance"}
    ):
        return "record_counseling"
    return "general_counseling"


def extract_condition_name(message: str, profile: Any | None) -> str | None:
    normalized = (message or "").strip()
    profile_conditions = split_text_items(getattr(profile, "conditions", None) if profile else None)
    generic_conditions = [
        "골다공증",
        "고혈압",
        "당뇨",
        "제2형 당뇨",
        "고지혈증",
        "빈혈",
        "천식",
        "알레르기 비염",
        "비염",
        "심부전",
        "역류성식도염",
        "위식도역류질환",
        "갑상선기능저하증",
    ]
    for condition in profile_conditions + generic_conditions:
        if condition and contains_keyword(normalized, condition):
            return condition
    return None


def is_profile_caution_query(message: str) -> bool:
    normalized = (message or "").strip()
    return contains_any(
        normalized,
        [
            "내 기록 기준",
            "지금 내 기록 기준",
            "건강기록 기준",
            "기록 기준",
            "주의할 점",
            "조심할 점",
            "내가 주의",
            "내 기록으로",
            "건강프로필 기준으로",
            "건강 프로필 기준으로",
        ],
    )


def is_guidance_query(message: str) -> bool:
    normalized = (message or "").strip()
    return contains_any(
        normalized,
        [
            "먼저 뭐 봐야",
            "먼저 봐야",
            "먼저 봐야 할",
            "먼저 무엇을 봐야",
            "먼저 확인해야",
            "어떻게 관리",
            "관리해야",
            "전반적으로 조언",
            "조언해줘",
            "생활관리에서",
            "생활 관리에서",
            "중요한 점",
            "제일 중요한 점",
            "무엇이 중요",
        ],
    )


def is_profile_body_query(message: str) -> bool:
    normalized = (message or "").strip()
    return contains_any(normalized, _PROFILE_BODY_KEYWORDS)


def is_profile_summary_query(message: str) -> bool:
    normalized = (message or "").strip()
    return contains_any(normalized, _PROFILE_SUMMARY_KEYWORDS) or (
        contains_any(normalized, ["전반적으로", "전반적", "요약"])
        and contains_any(normalized, ["건강프로필", "건강 프로필", "내 프로필"])
    )


def is_profile_related_query(message: str) -> bool:
    normalized = normalize_user_message(message)
    return (
        is_profile_body_query(normalized)
        or is_profile_summary_query(normalized)
        or contains_any(normalized, _PROFILE_RELATED_KEYWORDS)
    )


def detect_time_period(message: str) -> str | None:
    normalized = (message or "").strip()
    if contains_any(normalized, ["오늘 밤", "오늘 저녁", "자기 전", "취침 전", "밤에"]):
        return "night"
    if contains_any(normalized, ["저녁", "저녁 먹고", "저녁에"]):
        return "evening"
    if contains_any(normalized, ["아침", "아침에", "아침 먹고"]):
        return "morning"
    return None


def was_waiting_for_interaction_scope(
    recent_messages: list[Any],
    session_memory: Any | None = None,
) -> bool:
    if session_memory and getattr(session_memory, "pending_clarification", None) == "interaction_scope":
        return True
    for recent in reversed(recent_messages):
        role = str(getattr(recent, "role", "") or "")
        content = str(getattr(recent, "content", "") or "")
        if role == "assistant" and "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지" in content:
            return True
        if role == "user" and content.strip():
            break
    return False


def is_hospital_followup_query(message: str, session_memory: Any | None) -> bool:
    normalized = (message or "").strip()
    if not normalized or not session_memory:
        return False
    recent_topic = str(getattr(session_memory, "recent_topic", "") or "").strip()
    pending = str(getattr(session_memory, "pending_clarification", "") or "").strip()
    if recent_topic != "hospital_schedule" and pending != "hospital_schedule_clarification":
        return False
    if normalized in _AFFIRMATIVE_SHORT_REPLIES:
        return True
    if contains_any(
        normalized,
        ["그 다음", "그다음", "다다음", "다음 외래", "다음 진료", "다음 검사", "다음 일정", "그 일정", "그거"],
    ):
        return True
    return False


def should_reset_pending_clarification(message: str) -> bool:
    normalized = normalize_user_message(message)
    if not normalized:
        return False
    if contains_any(normalized, _CLARIFICATION_RESET_PREFIXES):
        return True
    if contains_any(normalized, _SYMPTOM_WORDS) and not contains_any(normalized, _CLARIFICATION_RESET_EXCLUDE_KEYWORDS):
        return True
    return False


def is_daily_message(message: str) -> bool:
    normalized = (message or "").strip()
    return contains_any(normalized, _DAILY_CHAT_KEYWORDS + _BOT_CAPABILITY_KEYWORDS)


def is_guide_summary_query(message: str) -> bool:
    return contains_any((message or "").strip(), _GUIDE_SUMMARY_KEYWORDS)


def is_hospital_schedule_query(message: str) -> bool:
    return contains_any((message or "").strip(), _HOSPITAL_SCHEDULE_KEYWORDS)
