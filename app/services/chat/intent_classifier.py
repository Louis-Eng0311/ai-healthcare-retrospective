from __future__ import annotations

from app.services.chat.analyzers import is_profile_body_query, is_profile_summary_query
from app.services.chat.entity_extraction import extract_external_drug_name
from app.services.chat.keywords import (
    _ALLERGY_FOOD_KEYWORDS,
    _BOT_CAPABILITY_KEYWORDS,
    _CAREGIVER_CHECK_KEYWORDS,
    _CONDITION_TREATMENT_KEYWORDS,
    _DAILY_CHAT_KEYWORDS,
    _EMERGENCY_GUIDANCE_KEYWORDS,
    _GENERAL_CAUTION_KEYWORDS,
    _GUIDE_SUMMARY_KEYWORDS,
    _HOSPITAL_SCHEDULE_KEYWORDS,
    _LIFESTYLE_TOP_KEYWORDS,
    _MED_DETAIL_KEYWORDS,
    _MED_LIST_KEYWORDS,
    _MED_REGULARITY_KEYWORDS,
    _MED_TIME_SPLIT_KEYWORDS,
    _MEDICATION_CAUTION_KEYWORDS,
    _MISSED_DOSE_KEYWORDS,
    _PRN_KEYWORDS,
    _PROFILE_ALCOHOL_KEYWORDS,
    _PROFILE_ALLERGY_KEYWORDS,
    _PROFILE_CONDITION_KEYWORDS,
    _PROFILE_EXERCISE_KEYWORDS,
    _PROFILE_HOSPITALIZATION_KEYWORDS,
    _PROFILE_SLEEP_KEYWORDS,
    _PROFILE_SMOKING_KEYWORDS,
    _RASH_KEYWORDS,
    _SCHEDULE_KEYWORDS,
    _SESSION_SUMMARY_KEYWORDS,
)
from app.services.chat.text_utils import append_unique, contains_any


def _apply_profile_rules(*, normalized: str, intents: list[str]) -> None:
    profile_rules = [
        (_PROFILE_SMOKING_KEYWORDS, "profile_smoking"),
        (_PROFILE_ALCOHOL_KEYWORDS, "profile_alcohol"),
        (_PROFILE_SLEEP_KEYWORDS, "profile_sleep"),
        (_PROFILE_EXERCISE_KEYWORDS, "profile_exercise"),
        (_PROFILE_CONDITION_KEYWORDS, "profile_conditions"),
        (_PROFILE_ALLERGY_KEYWORDS, "profile_allergies"),
        (_PROFILE_HOSPITALIZATION_KEYWORDS, "profile_hospitalization"),
    ]
    for keywords, intent in profile_rules:
        if contains_any(normalized, keywords):
            append_unique(intents, intent)
    if is_profile_body_query(normalized):
        append_unique(intents, "profile_body")
    if is_profile_summary_query(normalized):
        append_unique(intents, "profile_summary")


def _apply_medication_pattern_rules(*, normalized: str, intents: list[str]) -> None:
    if contains_any(normalized, _MED_DETAIL_KEYWORDS) and contains_any(normalized, ["언제 먹", "언제 복용", "몇 시", "시간"]):
        append_unique(intents, "med_detail")
    if contains_any(normalized, _MED_TIME_SPLIT_KEYWORDS) or (
        contains_any(normalized, ["아침", "오전"])
        and contains_any(normalized, ["저녁", "오후", "취침 전"])
        and contains_any(normalized, ["나눠", "구분"])
    ):
        append_unique(intents, "med_time_split")
    if contains_any(normalized, _MED_REGULARITY_KEYWORDS):
        append_unique(intents, "med_regularity")
    if contains_any(normalized, _PRN_KEYWORDS):
        append_unique(intents, "med_prn")
    if contains_any(normalized, _MED_DETAIL_KEYWORDS):
        append_unique(intents, "med_detail")
    if contains_any(normalized, ["같이", "상호작용", "함께"]) and contains_any(normalized, _MEDICATION_CAUTION_KEYWORDS):
        append_unique(intents, "medication_caution")


def _apply_medication_caution_rules(*, normalized: str, intents: list[str]) -> None:
    if contains_any(normalized, _MEDICATION_CAUTION_KEYWORDS) or (
        contains_any(normalized, ["주의"]) and contains_any(normalized, ["약"])
    ):
        append_unique(intents, "medication_caution")
    if contains_any(normalized, _MED_LIST_KEYWORDS):
        append_unique(intents, "med_list")


def _apply_medication_entity_rules(*, normalized: str, intents: list[str], external_drug_name: str | None) -> None:
    if external_drug_name or contains_any(normalized, ["약에 대해서 궁금", "라는 약", "라고 알아", "약 알아", "약이 궁금"]):
        append_unique(intents, "external_med")
    if contains_any(normalized, _CONDITION_TREATMENT_KEYWORDS) and "external_med" not in intents:
        append_unique(intents, "condition_general")


def _apply_medication_rules(*, normalized: str, intents: list[str], external_drug_name: str | None) -> None:
    _apply_medication_pattern_rules(normalized=normalized, intents=intents)
    _apply_medication_caution_rules(normalized=normalized, intents=intents)
    _apply_medication_entity_rules(normalized=normalized, intents=intents, external_drug_name=external_drug_name)


def _apply_schedule_rules(*, normalized: str, intents: list[str]) -> None:
    if contains_any(normalized, _HOSPITAL_SCHEDULE_KEYWORDS):
        append_unique(intents, "hospital_schedule")
    if contains_any(normalized, _SCHEDULE_KEYWORDS):
        append_unique(intents, "schedule")


def _apply_safety_rules(*, normalized: str, intents: list[str]) -> None:
    if contains_any(normalized, ["두드러기", "발진"]) and contains_any(normalized, ["약 먹고", "복용", "약 먹은 뒤"]):
        append_unique(intents, "rash")
    if contains_any(normalized, _RASH_KEYWORDS):
        append_unique(intents, "rash")
    if contains_any(normalized, ["음식", "알레르기"]) and contains_any(normalized, ["조심", "주의"]):
        append_unique(intents, "allergy_food")
    if contains_any(normalized, _ALLERGY_FOOD_KEYWORDS):
        append_unique(intents, "allergy_food")
    if contains_any(normalized, _MISSED_DOSE_KEYWORDS):
        append_unique(intents, "missed_dose")
    if contains_any(normalized, _EMERGENCY_GUIDANCE_KEYWORDS):
        append_unique(intents, "emergency_guidance")
    if contains_any(normalized, _GENERAL_CAUTION_KEYWORDS):
        append_unique(intents, "general_caution")


def _apply_conversation_rules(*, normalized: str, intents: list[str]) -> None:
    if contains_any(normalized, _DAILY_CHAT_KEYWORDS) or contains_any(normalized, _BOT_CAPABILITY_KEYWORDS):
        append_unique(intents, "daily")
    if contains_any(normalized, _CAREGIVER_CHECK_KEYWORDS):
        append_unique(intents, "caregiver_check")
    if contains_any(normalized, ["3가지만", "세 가지만"]) and contains_any(normalized, ["생활"]):
        append_unique(intents, "lifestyle_top")
    if contains_any(normalized, _LIFESTYLE_TOP_KEYWORDS):
        append_unique(intents, "lifestyle_top")
    if contains_any(normalized, _SESSION_SUMMARY_KEYWORDS):
        append_unique(intents, "session_summary")
    if contains_any(normalized, _GUIDE_SUMMARY_KEYWORDS):
        append_unique(intents, "guide")


def analyze_intents(message: str) -> list[str]:
    normalized = (message or "").strip()
    intents: list[str] = []
    external_drug_name = extract_external_drug_name(normalized, None)

    _apply_profile_rules(normalized=normalized, intents=intents)
    _apply_medication_rules(normalized=normalized, intents=intents, external_drug_name=external_drug_name)
    _apply_schedule_rules(normalized=normalized, intents=intents)
    _apply_safety_rules(normalized=normalized, intents=intents)
    _apply_conversation_rules(normalized=normalized, intents=intents)

    return intents or ["general"]


def detect_intent(message: str) -> str:
    return analyze_intents(message)[0]
