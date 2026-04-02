from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.chat.analyzers import (
    detect_time_period,
    extract_condition_name,
    is_guidance_query,
    is_hospital_followup_query,
    is_profile_body_query,
    is_profile_caution_query,
    is_profile_related_query,
    is_profile_summary_query,
    resolve_answer_mode,
    should_reset_pending_clarification,
    was_waiting_for_interaction_scope,
)
from app.services.chat.keywords import (
    _ADHERENCE_PRIORITY_KEYWORDS,
    _ALLERGY_FOOD_KEYWORDS,
    _BOT_CAPABILITY_KEYWORDS,
    _CAREGIVER_CHECK_KEYWORDS,
    _COLD_MED_CAUTION_KEYWORDS,
    _CONDITION_TREATMENT_KEYWORDS,
    _DAILY_CHAT_KEYWORDS,
    _EMERGENCY_GUIDANCE_KEYWORDS,
    _EXTERNAL_DRUG_SUFFIXES,
    _FIRST_CHECK_KEYWORDS,
    _FOLLOWUP_MED_REFERENCES,
    _GUIDE_SUMMARY_KEYWORDS,
    _HOSPITAL_SCHEDULE_KEYWORDS,
    _LIFESTYLE_TOP_KEYWORDS,
    _MED_DETAIL_KEYWORDS,
    _MED_LIST_KEYWORDS,
    _MED_REGULARITY_KEYWORDS,
    _MED_TIME_SPLIT_KEYWORDS,
    _MEDICATION_CAUTION_KEYWORDS,
    _MISSED_DOSE_KEYWORDS,
    _OBSERVATION_CHECK_KEYWORDS,
    _PRN_KEYWORDS,
    _PROFILE_ALCOHOL_KEYWORDS,
    _PROFILE_EXERCISE_KEYWORDS,
    _PROFILE_SLEEP_KEYWORDS,
    _PROFILE_SMOKING_KEYWORDS,
    _RASH_KEYWORDS,
    _SCHEDULE_KEYWORDS,
    _SCHEDULE_ORDER_KEYWORDS,
    _SCHOOL_OBSERVATION_KEYWORDS,
    _SESSION_SUMMARY_KEYWORDS,
    _SYMPTOM_CAUSE_KEYWORDS,
    _SYMPTOM_GUIDANCE_KEYWORDS,
    _SYMPTOM_WORDS,
    _TONIGHT_CHECK_KEYWORDS,
)
from app.services.chat.quality import normalize_user_message
from app.services.chat.text_utils import contains_any, extract_bracketed_drug_name

_MED_INTERACTION_ACTION_KEYWORDS = ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "조합", "상호작용"]
_CURRENT_MEDS_QUERY_KEYWORDS = _MED_LIST_KEYWORDS + [
    "오늘 약",
    "오늘 먹는 약",
    "오늘 복용약",
    "지금 먹는 약",
    "현재 먹는 약",
    "현재 약",
    "복용약",
]


def _extract_external_drug_candidate(
    *,
    normalized: str,
    target_med: dict[str, Any] | None,
    recent_messages: list[Any],
    session_memory: Any | None,
    extract_external_drug_name_fn: Callable[..., str | None],
) -> str | None:
    if target_med:
        return None
    return extract_external_drug_name_fn(
        normalized,
        recent_messages,
        session_memory=session_memory,
    )


def _should_skip_external_extraction(
    *,
    normalized: str,
    session_memory: Any | None,
) -> tuple[bool, bool, bool, bool, bool]:
    profile_query = is_profile_related_query(normalized)
    hospital_query = contains_any(normalized, _HOSPITAL_SCHEDULE_KEYWORDS)
    hospital_followup_query = is_hospital_followup_query(normalized, session_memory)
    med_list_query = contains_any(normalized, _MED_LIST_KEYWORDS)
    current_meds_interaction_query = contains_any(normalized, _CURRENT_MEDS_QUERY_KEYWORDS) and contains_any(
        normalized,
        ["같이", "상호작용", "함께", "조합", "조심", "주의", "같이 먹", "함께 먹"],
    )
    return (
        profile_query,
        hospital_query,
        hospital_followup_query,
        med_list_query,
        current_meds_interaction_query,
    )


def _build_interaction_scope_override(
    *,
    normalized: str,
    reset_pending_clarification: bool,
    recent_messages: list[Any],
    session_memory: Any | None,
    target_condition: str | None,
    time_period: str | None,
    is_emergency: bool,
    emergency_message: str | None,
) -> dict[str, Any] | None:
    if reset_pending_clarification:
        return None
    if not was_waiting_for_interaction_scope(recent_messages, session_memory):
        return None
    if not contains_any(normalized, ["현재 복용약끼리", "현재 약끼리", "복용약끼리", "현재 먹는 약끼리"]):
        return None
    intents = ["medication_caution"]
    return {
        "raw_message": normalized,
        "intents": intents,
        "primary_intent": "medication_caution",
        "target_med": None,
        "external_drug_name": None,
        "target_condition": target_condition,
        "time_period": time_period,
        "is_emergency": is_emergency,
        "emergency_message": emergency_message,
        "answer_mode": "record_counseling",
    }


def _resolve_top_level_priority_intents(*, normalized: str, is_emergency: bool) -> list[str] | None:
    if is_emergency:
        return ["emergency"]
    if contains_any(normalized, _DAILY_CHAT_KEYWORDS + _BOT_CAPABILITY_KEYWORDS):
        return ["daily"]
    if contains_any(normalized, _MISSED_DOSE_KEYWORDS):
        if contains_any(normalized, _EMERGENCY_GUIDANCE_KEYWORDS):
            return ["missed_dose", "emergency_guidance"]
        return ["missed_dose"]
    if contains_any(normalized, _RASH_KEYWORDS):
        return ["rash"]
    return None


def _resolve_bracket_priority_intents(
    *,
    bracketed_drug_name: str | None,
    target_med: dict[str, Any] | None,
    session_memory: Any | None,
) -> list[str] | None:
    if not bracketed_drug_name:
        return None
    recent_topic = str(getattr(session_memory, "recent_topic", "") or "").strip()
    pending = str(getattr(session_memory, "pending_clarification", "") or "").strip()
    if target_med and recent_topic == "med_schedule":
        return ["med_detail", "schedule"]
    if target_med and pending == "interaction_scope":
        return ["medication_caution", "med_detail"]
    if pending == "interaction_scope":
        return ["medication_caution", "external_med"]
    return ["med_detail"] if target_med else ["external_med"]


def _resolve_pre_profile_priority_intents(
    *,
    normalized: str,
    current_meds_interaction_query: bool,
    explicit_new_drug_interaction_query: bool,
    explicit_external_caution_query: bool,
) -> list[str] | None:
    if current_meds_interaction_query:
        return ["medication_caution", "med_list"]
    if explicit_new_drug_interaction_query:
        return ["medication_caution", "external_med"]
    if explicit_external_caution_query:
        return ["external_med"]
    if is_guidance_query(normalized):
        return ["profile_guidance"]
    if is_profile_summary_query(normalized):
        intents = ["profile_summary"]
        if contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
            intents.append("profile_sleep")
        if contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
            intents.append("profile_exercise")
        return intents
    return None


def _resolve_priority_intents(
    *,
    normalized: str,
    is_emergency: bool,
    bracketed_drug_name: str | None,
    target_med: dict[str, Any] | None,
    current_meds_interaction_query: bool,
    explicit_new_drug_interaction_query: bool,
    explicit_external_caution_query: bool,
    session_memory: Any | None,
) -> list[str] | None:
    for resolver in (
        lambda: _resolve_top_level_priority_intents(normalized=normalized, is_emergency=is_emergency),
        lambda: _resolve_bracket_priority_intents(
            bracketed_drug_name=bracketed_drug_name,
            target_med=target_med,
            session_memory=session_memory,
        ),
        lambda: _resolve_pre_profile_priority_intents(
            normalized=normalized,
            current_meds_interaction_query=current_meds_interaction_query,
            explicit_new_drug_interaction_query=explicit_new_drug_interaction_query,
            explicit_external_caution_query=explicit_external_caution_query,
        ),
    ):
        intents = resolver()
        if intents is not None:
            return intents
    return None


def _resolve_domain_intents(
    *,
    normalized: str,
    hospital_query: bool,
    hospital_followup_query: bool,
    external_drug_name: str | None,
    target_condition: str | None,
    target_med: dict[str, Any] | None,
) -> list[str] | None:
    if hospital_query or hospital_followup_query:
        return ["hospital_schedule"]
    if is_profile_body_query(normalized):
        intents = ["profile_body"]
        if contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
            intents.append("profile_sleep")
        if contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
            intents.append("profile_exercise")
        return intents
    if external_drug_name:
        caution_keywords = _MEDICATION_CAUTION_KEYWORDS + _COLD_MED_CAUTION_KEYWORDS + [
            "같이 먹",
            "함께 먹",
            "추가로 먹",
            "먹어도 돼",
            "복용해도 돼",
            "괜찮아",
            "같이 복용",
        ]
        return ["medication_caution", "external_med"] if contains_any(normalized, caution_keywords) else ["external_med"]
    if target_condition and contains_any(normalized, _CONDITION_TREATMENT_KEYWORDS + _MED_DETAIL_KEYWORDS):
        return ["condition_general"]
    if is_profile_caution_query(normalized):
        return ["general_caution"]
    return None


def _resolve_schedule_priority_intents(
    *,
    normalized: str,
) -> list[str] | None:
    if contains_any(normalized, _TONIGHT_CHECK_KEYWORDS + ["오늘 약", "오늘 먹을 약", "오늘 복용할 약", "오늘 내가 먹어야 할 약"]):
        return ["tonight_check"]
    if contains_any(normalized, _SCHEDULE_ORDER_KEYWORDS):
        return ["schedule_order"]
    if contains_any(
        normalized,
        _ADHERENCE_PRIORITY_KEYWORDS + ["안 빼먹어야", "꼭 안 빼먹어야", "꼭 챙겨야", "자주 놓치는 약", "자주 놓치", "놓치는 약"],
    ):
        return ["adherence_priority"]
    if contains_any(normalized, _SCHOOL_OBSERVATION_KEYWORDS):
        return ["school_observation"]
    if contains_any(normalized, _COLD_MED_CAUTION_KEYWORDS):
        return ["cold_med_caution"]
    return None


def _resolve_symptom_priority_intents(*, normalized: str, target_med: dict[str, Any] | None) -> list[str] | None:
    if target_med and contains_any(normalized, _OBSERVATION_CHECK_KEYWORDS + _SYMPTOM_WORDS):
        return ["observation_check"]
    if contains_any(normalized, _SYMPTOM_WORDS) and contains_any(normalized, _SYMPTOM_GUIDANCE_KEYWORDS):
        return ["symptom_cause"]
    if contains_any(normalized, _SYMPTOM_WORDS) and contains_any(normalized, _SYMPTOM_CAUSE_KEYWORDS + _FIRST_CHECK_KEYWORDS):
        return ["symptom_cause"]
    return None


def _resolve_med_reference_priority_intents(
    *,
    normalized: str,
    med_list_query: bool,
    target_med: dict[str, Any] | None,
) -> list[str] | None:
    if contains_any(normalized, _FOLLOWUP_MED_REFERENCES) and contains_any(normalized, _SCHEDULE_KEYWORDS + _MED_TIME_SPLIT_KEYWORDS):
        return ["med_detail", "schedule"]
    if target_med and contains_any(normalized, _SCHEDULE_KEYWORDS + _MED_TIME_SPLIT_KEYWORDS):
        return ["med_detail", "schedule"]
    if target_med:
        intents = ["med_detail"]
        if contains_any(normalized, _MEDICATION_CAUTION_KEYWORDS):
            intents.append("medication_caution")
        if contains_any(normalized, _PRN_KEYWORDS + _MED_REGULARITY_KEYWORDS):
            intents.append("med_prn")
        return intents
    if med_list_query:
        intents = ["med_list"]
        if contains_any(normalized, _MED_TIME_SPLIT_KEYWORDS):
            intents.append("med_time_split")
        if contains_any(normalized, _MED_REGULARITY_KEYWORDS):
            intents.append("med_regularity")
        return intents
    return None


def _resolve_profile_fallback_intents(*, normalized: str) -> list[str] | None:
    profile_rules = [
        (_PROFILE_ALCOHOL_KEYWORDS, ["profile_alcohol"]),
        (_PROFILE_SMOKING_KEYWORDS, ["profile_smoking"]),
        (_CAREGIVER_CHECK_KEYWORDS, ["caregiver_check"]),
        (_ALLERGY_FOOD_KEYWORDS, ["allergy_food"]),
        (_SCHEDULE_KEYWORDS, ["schedule"]),
        (_SESSION_SUMMARY_KEYWORDS, ["session_summary"]),
    ]
    if contains_any(normalized, _LIFESTYLE_TOP_KEYWORDS):
        return ["lifestyle_top"]
    if is_guidance_query(normalized) and contains_any(
        normalized,
        _PROFILE_SLEEP_KEYWORDS + _PROFILE_EXERCISE_KEYWORDS + ["건강프로필", "건강 프로필"],
    ):
        return ["profile_guidance"]
    if contains_any(normalized, _PROFILE_SLEEP_KEYWORDS) and contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
        return ["profile_sleep", "profile_exercise"]
    if contains_any(normalized, _PROFILE_SLEEP_KEYWORDS):
        return ["profile_sleep"]
    if contains_any(normalized, _PROFILE_EXERCISE_KEYWORDS):
        return ["profile_exercise"]
    for keywords, intents in profile_rules:
        if contains_any(normalized, keywords):
            return intents
    return None


def _resolve_fallback_intents(*, normalized: str, target_med: dict[str, Any] | None, external_drug_name: str | None) -> list[str]:
    profile_fallback = _resolve_profile_fallback_intents(normalized=normalized)
    if profile_fallback is not None:
        return profile_fallback
    if contains_any(normalized, _GUIDE_SUMMARY_KEYWORDS) and not target_med and not external_drug_name:
        return ["guide"]
    return ["general"]


def _resolve_raw_intents(
    *,
    normalized: str,
    is_emergency: bool,
    bracketed_drug_name: str | None,
    target_med: dict[str, Any] | None,
    external_drug_name: str | None,
    current_meds_interaction_query: bool,
    explicit_new_drug_interaction_query: bool,
    explicit_external_caution_query: bool,
    session_memory: Any | None,
    hospital_query: bool,
    hospital_followup_query: bool,
    target_condition: str | None,
    med_list_query: bool,
) -> list[str]:
    for resolver in (
        lambda: _resolve_priority_intents(
            normalized=normalized,
            is_emergency=is_emergency,
            bracketed_drug_name=bracketed_drug_name,
            target_med=target_med,
            current_meds_interaction_query=current_meds_interaction_query,
            explicit_new_drug_interaction_query=explicit_new_drug_interaction_query,
            explicit_external_caution_query=explicit_external_caution_query,
            session_memory=session_memory,
        ),
        lambda: _resolve_domain_intents(
            normalized=normalized,
            hospital_query=hospital_query,
            hospital_followup_query=hospital_followup_query,
            external_drug_name=external_drug_name,
            target_condition=target_condition,
            target_med=target_med,
        ),
        lambda: _resolve_schedule_priority_intents(
            normalized=normalized,
        ),
        lambda: _resolve_symptom_priority_intents(
            normalized=normalized,
            target_med=target_med,
        ),
        lambda: _resolve_med_reference_priority_intents(
            normalized=normalized,
            med_list_query=med_list_query,
            target_med=target_med,
        ),
    ):
        intents = resolver()
        if intents is not None:
            return intents
    return _resolve_fallback_intents(
        normalized=normalized,
        target_med=target_med,
        external_drug_name=external_drug_name,
    )


def analyze_question_data(
    *,
    message: str,
    meds: list[dict[str, Any]],
    recent_messages: list[Any],
    requester_role: Any,
    profile: Any | None,
    session_memory: Any | None,
    extract_target_med: Callable[..., dict[str, Any] | None],
    extract_external_drug_name: Callable[..., str | None],
    detect_emergency: Callable[[str], tuple[bool, str | None]],
    normalize_intent_order: Callable[[list[str], Any], list[str]],
) -> dict[str, Any]:
    normalized = normalize_user_message(message)
    reset_pending_clarification = should_reset_pending_clarification(normalized)

    (
        profile_query,
        hospital_query,
        hospital_followup_query,
        med_list_query,
        current_meds_interaction_query,
    ) = _should_skip_external_extraction(normalized=normalized, session_memory=session_memory)

    target_med = extract_target_med(
        message=normalized,
        meds=meds,
        recent_messages=recent_messages,
        session_memory=session_memory,
    )
    external_drug_name = None
    if not (profile_query or hospital_query or hospital_followup_query or med_list_query or current_meds_interaction_query):
        external_drug_name = _extract_external_drug_candidate(
            normalized=normalized,
            target_med=target_med,
            recent_messages=recent_messages,
            session_memory=session_memory,
            extract_external_drug_name_fn=extract_external_drug_name,
        )

    explicit_external_caution_query = bool(
        external_drug_name
        and contains_any(normalized, ["주의사항", "주의할 점", "부작용", "용도", "무슨 약", "어떤 약", "뭐야"])
        and not contains_any(normalized, ["같이 먹", "함께 먹", "추가로 먹", "먹어도 돼", "복용해도 돼", "조합", "상호작용"])
    )
    explicit_new_drug_interaction_query = bool(
        contains_any(normalized, _MED_INTERACTION_ACTION_KEYWORDS + ["괜찮아"])
        and (external_drug_name or contains_any(normalized, ["새 감기약", "새 약", "감기약"]))
    )
    target_condition = extract_condition_name(normalized, profile)
    time_period = detect_time_period(normalized)
    bracketed_drug_name = extract_bracketed_drug_name(normalized)
    if target_condition and external_drug_name and not any(str(external_drug_name).endswith(suffix) for suffix in _EXTERNAL_DRUG_SUFFIXES):
        external_drug_name = None

    is_emergency, emergency_message = detect_emergency(normalized)
    interaction_override = _build_interaction_scope_override(
        normalized=normalized,
        reset_pending_clarification=reset_pending_clarification,
        recent_messages=recent_messages,
        session_memory=session_memory,
        target_condition=target_condition,
        time_period=time_period,
        is_emergency=is_emergency,
        emergency_message=emergency_message,
    )
    if interaction_override:
        return interaction_override

    raw_intents = _resolve_raw_intents(
        normalized=normalized,
        is_emergency=is_emergency,
        bracketed_drug_name=bracketed_drug_name,
        target_med=target_med,
        external_drug_name=external_drug_name,
        current_meds_interaction_query=current_meds_interaction_query,
        explicit_new_drug_interaction_query=explicit_new_drug_interaction_query,
        explicit_external_caution_query=explicit_external_caution_query,
        session_memory=session_memory,
        hospital_query=hospital_query,
        hospital_followup_query=hospital_followup_query,
        target_condition=target_condition,
        med_list_query=med_list_query,
    )

    intents = normalize_intent_order(raw_intents, requester_role)
    answer_mode = resolve_answer_mode(intents=intents, is_emergency=is_emergency)
    return {
        "raw_message": normalized,
        "intents": intents,
        "primary_intent": intents[0],
        "target_med": target_med,
        "external_drug_name": external_drug_name,
        "target_condition": target_condition,
        "time_period": time_period,
        "is_emergency": is_emergency,
        "emergency_message": emergency_message,
        "answer_mode": answer_mode,
    }
