from __future__ import annotations

from typing import Any


def normalize_intent_order(intents: list[str], requester_role: Any, caregiver_role: Any) -> list[str]:
    ordered: list[str] = []
    skip = set()

    if "external_med" in intents:
        skip.update({"med_detail", "general_caution", "allergy_food", "guide"})
    if "lifestyle_top" in intents:
        skip.update({"profile_sleep", "profile_exercise", "allergy_food"})
    if "profile_summary" in intents:
        skip.update({"guide", "session_summary"})
    if "med_time_split" in intents:
        skip.add("med_list")
    if "med_detail" in intents:
        skip.add("schedule")
    if requester_role != caregiver_role and "caregiver_check" in intents:
        intents = [intent for intent in intents if intent != "caregiver_check"] + ["self_check"]

    priority = [
        "rash",
        "missed_dose",
        "emergency_guidance",
        "self_check",
        "caregiver_check",
        "school_observation",
        "cold_med_caution",
        "external_med",
        "condition_general",
        "adherence_priority",
        "tonight_check",
        "schedule_order",
        "symptom_cause",
        "observation_check",
        "med_detail",
        "medication_caution",
        "general_caution",
        "profile_summary",
        "profile_body",
        "profile_guidance",
        "med_time_split",
        "med_regularity",
        "med_list",
        "hospital_schedule",
        "schedule",
        "allergy_food",
        "lifestyle_top",
        "session_summary",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "guide",
        "daily",
        "general",
    ]
    for key in priority:
        if key in intents and key not in skip and key not in ordered:
            ordered.append(key)
    for intent in intents:
        if intent not in skip and intent not in ordered:
            ordered.append(intent)
    return ordered
