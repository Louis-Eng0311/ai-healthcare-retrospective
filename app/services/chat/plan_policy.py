from __future__ import annotations

from typing import Any


def harmonize_chat_plan(*, analysis: Any, plan: Any | None, plan_factory: Any) -> Any | None:
    if not plan:
        return None
    primary = analysis.primary_intent
    if primary == "daily":
        return None
    if primary in {"external_med", "medication_caution", "profile_guidance", "tonight_check", "schedule_order", "adherence_priority"}:
        return None
    if primary == "hospital_schedule":
        plan.topic = "hospital_schedule"
        return plan
    if primary in {"med_detail", "med_prn", "med_time_split", "med_regularity"}:
        if analysis.target_med:
            plan.topic = "current_meds" if primary == "med_detail" else "med_schedule"
            plan.referenced_drug_name = str(analysis.target_med.get("display_name") or "").strip() or plan.referenced_drug_name
            return plan
        return None
    if primary in {"med_list", "schedule", "tonight_check", "schedule_order", "adherence_priority"}:
        plan.topic = "med_schedule" if primary != "med_list" else "current_meds"
        return plan
    if primary in {
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
    }:
        plan.topic = "profile"
        requested = set(plan.requested_fields)
        mapping = {
            "profile_body": {"body_metrics"},
            "profile_summary": {"summary"},
            "profile_guidance": {"guidance", "lifestyle", "risk"},
            "profile_smoking": {"smoking"},
            "profile_alcohol": {"alcohol"},
            "profile_sleep": {"sleep"},
            "profile_exercise": {"exercise"},
            "profile_conditions": {"conditions"},
            "profile_allergies": {"allergies"},
            "profile_hospitalization": {"hospitalization"},
        }
        requested = mapping[primary] if primary == "profile_guidance" else (requested | mapping[primary])
        plan.requested_fields = list(requested)
        return plan
    if primary == "condition_general":
        plan.topic = "condition_general"
        if analysis.target_condition and not plan.referenced_drug_name:
            plan.referenced_drug_name = analysis.target_condition
        return plan
    if primary in {"general_caution", "lifestyle_top", "session_summary", "self_check", "caregiver_check"}:
        return None
    return plan


def has_record_context(context: Any) -> bool:
    return bool(context.profile or context.meds or context.schedules or context.hospital_schedules or context.latest_guide)


def has_required_context_for_request(*, analysis: Any, plan: Any | None, context: Any) -> bool:
    primary = analysis.primary_intent
    topic = plan.topic if plan else ""
    if primary in {"daily", "general", "external_med", "condition_general", "guide"}:
        return True
    if primary in {
        "profile_body",
        "profile_summary",
        "profile_smoking",
        "profile_alcohol",
        "profile_sleep",
        "profile_exercise",
        "profile_conditions",
        "profile_allergies",
        "profile_hospitalization",
    }:
        return context.profile is not None
    if primary == "profile_guidance":
        return bool(context.profile or context.latest_guide or context.adherence_summary.get("total"))
    if primary in {
        "med_list",
        "med_detail",
        "med_time_split",
        "med_regularity",
        "med_prn",
        "schedule",
        "tonight_check",
        "schedule_order",
        "adherence_priority",
        "missed_dose",
        "self_check",
        "caregiver_check",
    }:
        return bool(context.meds or context.schedules or context.adherence_summary.get("total"))
    if primary == "medication_caution":
        return bool(context.meds or analysis.external_drug_name)
    if primary == "general_caution":
        return bool(context.profile or context.latest_guide or context.meds or context.schedules or context.adherence_summary.get("total"))
    if primary == "hospital_schedule":
        return bool(context.hospital_schedules)
    if primary in {"session_summary", "lifestyle_top"}:
        return has_record_context(context)
    if topic == "profile":
        return bool(context.profile or context.latest_guide or context.adherence_summary.get("total"))
    if topic in {"current_meds", "med_schedule", "drug_interaction"}:
        return bool(context.meds or context.schedules or context.adherence_summary.get("total"))
    if topic == "hospital_schedule":
        return bool(context.hospital_schedules)
    return has_record_context(context)


def resolve_data_readiness(context: Any) -> str:
    flags = [
        context.profile is not None,
        bool(context.meds),
        bool(context.schedules),
        bool(context.hospital_schedules),
        context.latest_guide is not None,
        bool(context.adherence_summary.get("total")),
    ]
    score = sum(flags)
    if score == 0:
        return "empty"
    if score <= 2:
        return "partial"
    return "rich"


def is_personalized_request(*, analysis: Any, plan: Any | None, personalized_intents: set[str]) -> bool:
    if analysis.primary_intent in personalized_intents:
        return True
    if analysis.primary_intent in {"daily", "general", "external_med", "condition_general"}:
        return False
    if plan and plan.topic in {"profile", "hospital_schedule", "current_meds", "med_schedule", "drug_interaction"}:
        return True
    return False


def build_record_required_reply(*, analysis: Any, target_label: str, requester_role: Any, audience: str, ops: dict[str, Any]) -> str:
    if analysis.primary_intent in {"daily", "general", "external_med", "condition_general"}:
        base = (
            "현재 기록이 충분하지 않아도 일반적인 기준으로는 안내드릴 수 있습니다. "
            "맞춤형 설명이 필요하면 건강 프로필이나 복약 정보를 더 등록해 주세요."
        )
        return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
    if analysis.primary_intent in {"med_list", "schedule", "med_detail", "medication_caution", "tonight_check", "schedule_order"}:
        base = (
            "현재 등록된 복약 정보가 없어 맞춤 복약 답변은 아직 어렵습니다. "
            "대신 일반적인 약 정보나 복용 시 주의점은 안내할 수 있습니다. 정확한 복약 상담을 원하시면 처방 문서나 복약 정보를 먼저 등록해 주세요."
        )
    elif analysis.primary_intent in {"profile_body", "profile_summary", "profile_guidance", "profile_sleep", "profile_exercise", "profile_conditions", "profile_allergies"}:
        base = (
            "현재 등록된 건강 프로필이 충분하지 않아 맞춤 건강 답변은 제한됩니다. "
            "건강 프로필을 입력하면 BMI, 수면, 운동, 알레르기, 기저질환 기준으로 더 정확히 안내드릴 수 있습니다."
        )
    elif analysis.primary_intent == "hospital_schedule":
        base = (
            "현재 연결된 병원 일정이 없어 맞춤 예약 확인은 어렵습니다. "
            "일정이 등록되면 다음 외래나 검사 일정을 바로 안내드릴 수 있습니다."
        )
    else:
        base = (
            f"{target_label} 기준 기록이 아직 충분하지 않아 개인화 답변은 제한됩니다. "
            "일반적인 약 정보나 건강 정보는 안내할 수 있고, 건강 프로필이나 처방 문서를 등록하면 더 정확히 도와드릴 수 있습니다."
        )
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
