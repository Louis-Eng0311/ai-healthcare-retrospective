from __future__ import annotations

from typing import Any


async def update_session_memory(
    *,
    session_id: int,
    analysis: Any,
    plan: Any | None,
    assistant_content: str,
    context: Any,
    ops: dict[str, Any],
) -> None:
    memory = context.session_memory or await ops["memory_model"].get_or_none(session_id=session_id)
    if not memory:
        memory = await ops["memory_model"].create(session_id=session_id)

    topic = plan.topic if plan and plan.topic else analysis.primary_intent
    memory.recent_topic = str(topic or "")[:50] or None

    target_med_name = None
    if analysis.target_med:
        target_med_name = str(analysis.target_med.get("display_name") or "").strip() or None
    if not target_med_name and analysis.primary_intent in {"tonight_check", "schedule_order", "adherence_priority", "schedule"}:
        for med in context.meds:
            name = str(med.get("display_name") or "").strip()
            if name and name in assistant_content:
                target_med_name = name
                break
    if target_med_name:
        memory.recent_drug_name = target_med_name

    external_name = analysis.external_drug_name or (plan.referenced_drug_name if plan else None)
    if external_name:
        memory.recent_external_drug_name = str(external_name).strip()[:255] or None

    if analysis.primary_intent.startswith("profile") or (plan and plan.topic == "profile"):
        focus = plan.requested_fields if plan and plan.requested_fields else analysis.intents
        memory.recent_profile_focus = ", ".join(focus[:5])[:255] or None

    if analysis.primary_intent == "hospital_schedule" or (plan and plan.topic == "hospital_schedule"):
        normalized = str(analysis.raw_message or "").strip()
        if ops["contains_any"](normalized, ["검사"]):
            memory.recent_hospital_focus = "검사 일정"
        elif ops["contains_any"](normalized, ["외래", "진료"]):
            memory.recent_hospital_focus = "외래/진료 일정"
        else:
            memory.recent_hospital_focus = "가장 가까운 병원 일정"

    pending_clarification = None
    clarification_question = None
    if plan and plan.needs_clarification and plan.clarification_question:
        clarification_question = plan.clarification_question
        pending_clarification = "interaction_scope" if plan.topic == "drug_interaction" else f"{plan.topic}_clarification"
    elif "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지" in assistant_content:
        pending_clarification = "interaction_scope"
        clarification_question = "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지 먼저 알려 주세요."

    memory.pending_clarification = pending_clarification
    memory.clarification_question = clarification_question
    await memory.save()
    context.session_memory = memory
