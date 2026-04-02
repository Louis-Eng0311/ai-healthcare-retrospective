from __future__ import annotations

from typing import Any

_PROFILE_INTENTS = {
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
}


def _clear_clarification(plan: Any, plan_factory: Any) -> Any:
    return plan_factory(
        topic=plan.topic,
        requested_fields=plan.requested_fields,
        referenced_drug_name=plan.referenced_drug_name,
        needs_clarification=False,
        clarification_question=None,
        use_record_data=plan.use_record_data,
        answer_style=plan.answer_style,
    )


def _normalize_plan_for_context(*, plan: Any, context: Any, plan_factory: Any) -> Any:
    if (
        plan.topic == "drug_interaction"
        and plan.needs_clarification
        and not plan.referenced_drug_name
        and len([str(med.get("display_name") or "").strip() for med in context.meds if str(med.get("display_name") or "").strip()]) >= 2
    ):
        return _clear_clarification(plan, plan_factory)
    if plan.topic == "med_schedule" and plan.needs_clarification and context.schedules:
        return _clear_clarification(plan, plan_factory)
    return plan


def _build_clarification_reply(*, plan: Any, requester_role: Any, audience: str, ops: dict[str, Any]) -> str | None:
    if not (plan.needs_clarification and plan.clarification_question):
        return None
    if requester_role == ops["caregiver_role"]:
        return ops["to_caregiver_style"](answer=plan.clarification_question, audience=audience)
    return plan.clarification_question


def _append_profile_answer(
    *,
    answers: list[str],
    intent: str,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> None:
    answer = ops["answer_profile_intent"](
        intent=intent,
        profile=context.profile,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )
    if answer:
        answers.append(answer)


def _render_profile_reply(
    *,
    plan: Any,
    message: str,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    requested = set(plan.requested_fields)
    answers: list[str] = []

    if "summary" in requested and "guidance" not in requested:
        _append_profile_answer(
            answers=answers,
            intent="profile_summary",
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
        return ops["compose_answers"](answers=answers, requester_role=requester_role, audience=audience)

    profile_field_map = [
        ("sleep", "profile_sleep"),
        ("exercise", "profile_exercise"),
        ("smoking", "profile_smoking"),
        ("alcohol", "profile_alcohol"),
        ("conditions", "profile_conditions"),
        ("allergies", "profile_allergies"),
        ("hospitalization", "profile_hospitalization"),
    ]

    if requested & {"bmi", "height", "weight", "body_metrics"}:
        _append_profile_answer(
            answers=answers,
            intent="profile_body",
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    for field, intent in profile_field_map:
        if field in requested:
            _append_profile_answer(
                answers=answers,
                intent=intent,
                context=context,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
                ops=ops,
            )

    if requested & {"guidance", "lifestyle", "risk"} or plan.answer_style in {"guidance", "advice"}:
        guidance = ops["answer_profile_guidance_intent"](
            message=message,
            profile=context.profile,
            guide=context.latest_guide,
            adherence_summary=context.adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        if guidance:
            answers.append(guidance)

    return ops["compose_answers"](answers=answers, requester_role=requester_role, audience=audience)


def _find_referenced_med(*, referenced_drug_name: str | None, context: Any, ops: dict[str, Any]) -> Any | None:
    if not referenced_drug_name:
        return None
    return ops["extract_target_med"](
        message=referenced_drug_name,
        meds=context.meds,
        recent_messages=context.recent_messages,
        session_memory=context.session_memory,
    )


async def _answer_referenced_med_detail(
    *,
    referenced_drug_name: str,
    matched_med: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    return await ops["answer_med_detail_intent"](
        message=referenced_drug_name,
        meds=context.meds,
        schedules=context.schedules,
        recent_messages=context.recent_messages,
        session_memory=context.session_memory,
        matched_med=matched_med,
        dur_alerts=context.dur_alerts,
        adherence_summary=context.adherence_summary,
        guide=context.latest_guide,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )


async def _render_current_meds_reply(
    *,
    plan: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    matched_med = _find_referenced_med(
        referenced_drug_name=plan.referenced_drug_name,
        context=context,
        ops=ops,
    )
    if matched_med and plan.referenced_drug_name:
        return await _answer_referenced_med_detail(
            referenced_drug_name=plan.referenced_drug_name,
            matched_med=matched_med,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    return ops["answer_med_list_intent"](
        meds=context.meds,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )


async def _render_med_schedule_reply(
    *,
    plan: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    matched_med = _find_referenced_med(
        referenced_drug_name=plan.referenced_drug_name,
        context=context,
        ops=ops,
    )
    if matched_med and plan.referenced_drug_name:
        return await _answer_referenced_med_detail(
            referenced_drug_name=plan.referenced_drug_name,
            matched_med=matched_med,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    return ops["answer_schedule_intent"](
        meds=context.meds,
        schedules=context.schedules,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )


async def _render_drug_interaction_reply(
    *,
    plan: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    if plan.referenced_drug_name:
        return await ops["answer_external_interaction_intent"](
            external_drug_name=plan.referenced_drug_name,
            meds=context.meds,
            profile=context.profile,
            adherence_summary=context.adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    return ops["answer_drug_interaction_overview"](
        meds=context.meds,
        adherence_summary=context.adherence_summary,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )


async def render_planned_reply(
    *,
    plan: Any | None,
    message: str,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    plan_factory: Any,
    ops: dict[str, Any],
) -> str | None:
    if not plan:
        return None

    plan = _normalize_plan_for_context(plan=plan, context=context, plan_factory=plan_factory)
    clarification = _build_clarification_reply(plan=plan, requester_role=requester_role, audience=audience, ops=ops)
    if clarification:
        return clarification

    topic = plan.topic
    if topic == "profile":
        return _render_profile_reply(
            plan=plan,
            message=message,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    if topic == "condition_general":
        return ops["answer_condition_general_intent"](
            condition_name=plan.referenced_drug_name or None,
            meds=context.meds,
            schedules=context.schedules,
            profile=context.profile,
            message=message,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    if topic == "hospital_schedule":
        return ops["answer_hospital_schedule_intent"](
            hospital_schedules=context.hospital_schedules,
            message=message,
            session_memory=context.session_memory,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    if topic == "current_meds":
        return await _render_current_meds_reply(
            plan=plan,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    if topic == "med_schedule":
        return await _render_med_schedule_reply(
            plan=plan,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    if topic == "external_drug":
        return await ops["answer_external_med_intent"](
            message=message,
            meds=context.meds,
            schedules=context.schedules,
            recent_messages=context.recent_messages,
            profile=context.profile,
            external_drug_name=plan.referenced_drug_name,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    if topic == "drug_interaction":
        return await _render_drug_interaction_reply(
            plan=plan,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
    return None


def _resolve_profile_deterministic_answer(
    *,
    current_intent: str,
    analysis: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    if current_intent not in _PROFILE_INTENTS:
        return None
    if current_intent == "profile_guidance":
        return ops["answer_profile_guidance_intent"](
            message=analysis.raw_message,
            profile=context.profile,
            guide=context.latest_guide,
            adherence_summary=context.adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    return ops["answer_profile_intent"](
        intent=current_intent,
        profile=context.profile,
        target_label=target_label,
        requester_role=requester_role,
        audience=audience,
    )


async def _resolve_async_deterministic_answer(
    *,
    current_intent: str,
    analysis: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    if current_intent == "med_detail":
        return await ops["answer_med_detail_intent"](
            message=analysis.raw_message,
            meds=context.meds,
            schedules=context.schedules,
            recent_messages=context.recent_messages,
            session_memory=context.session_memory,
            matched_med=analysis.target_med,
            dur_alerts=context.dur_alerts,
            adherence_summary=context.adherence_summary,
            guide=context.latest_guide,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    if current_intent == "medication_caution":
        return await ops["answer_medication_caution_intent"](
            message=analysis.raw_message,
            guide=context.latest_guide,
            meds=context.meds,
            profile=context.profile,
            dur_alerts=context.dur_alerts,
            adherence_summary=context.adherence_summary,
            recent_messages=context.recent_messages,
            matched_med=analysis.target_med,
            external_drug_name=analysis.external_drug_name,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    if current_intent == "external_med":
        return await ops["answer_external_med_intent"](
            message=analysis.raw_message,
            meds=context.meds,
            schedules=context.schedules,
            recent_messages=context.recent_messages,
            profile=context.profile,
            external_drug_name=analysis.external_drug_name,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
    return None


def _resolve_sync_deterministic_answer(
    *,
    current_intent: str,
    analysis: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    common = {
        "target_label": target_label,
        "requester_role": requester_role,
        "audience": audience,
    }
    simple_handlers: dict[str, Any] = {
        "med_time_split": lambda: ops["answer_med_time_split_intent"](meds=context.meds, schedules=context.schedules, **common),
        "med_regularity": lambda: ops["answer_med_regularity_intent"](meds=context.meds, schedules=context.schedules, **common),
        "med_list": lambda: ops["answer_med_list_intent"](meds=context.meds, **common),
        "caregiver_check": lambda: ops["answer_caregiver_check_intent"](
            guide=context.latest_guide, meds=context.meds, schedules=context.schedules, **common
        ),
        "self_check": lambda: ops["answer_self_check_intent"](guide=context.latest_guide, meds=context.meds, schedules=context.schedules, **common),
        "allergy_food": lambda: ops["answer_allergy_food_intent"](profile=context.profile, **common),
        "missed_dose": lambda: ops["answer_missed_dose_intent"](**common),
        "emergency_guidance": lambda: ops["answer_emergency_guidance_intent"](**common),
        "lifestyle_top": lambda: ops["answer_lifestyle_top_intent"](
            guide=context.latest_guide, profile=context.profile, adherence_summary=context.adherence_summary, **common
        ),
        "session_summary": lambda: ops["answer_session_summary_intent"](
            meds=context.meds, profile=context.profile, adherence_summary=context.adherence_summary, **common
        ),
        "tonight_check": lambda: ops["answer_tonight_check_intent"](
            meds=context.meds, schedules=context.schedules, adherence_summary=context.adherence_summary, **common
        ),
        "adherence_priority": lambda: ops["answer_adherence_priority_intent"](
            meds=context.meds, schedules=context.schedules, adherence_summary=context.adherence_summary, **common
        ),
        "school_observation": lambda: ops["answer_school_observation_intent"](profile=context.profile, **common),
        "cold_med_caution": lambda: ops["answer_cold_med_caution_intent"](profile=context.profile, meds=context.meds, **common),
        "rash": lambda: ops["answer_rash_intent"](**common),
        "schedule": lambda: ops["answer_schedule_intent"](meds=context.meds, schedules=context.schedules, **common),
        "guide": lambda: ops["answer_guide_intent"](guide=context.latest_guide, **common),
        "daily": lambda: ops["answer_daily_chat"](
            message=analysis.raw_message,
            requester_role=requester_role,
            target_label=target_label,
            data_readiness=ops["resolve_data_readiness"](context),
        ),
    }
    if current_intent in simple_handlers:
        return simple_handlers[current_intent]()

    if current_intent == "med_prn":
        return ops["answer_med_prn_intent"](
            message=analysis.raw_message,
            meds=context.meds,
            schedules=context.schedules,
            recent_messages=context.recent_messages,
            **common,
        )
    if current_intent == "schedule_order":
        return ops["answer_schedule_order_intent"](
            meds=context.meds,
            schedules=context.schedules,
            time_period=analysis.time_period,
            **common,
        )
    if current_intent == "symptom_cause":
        return ops["answer_symptom_cause_intent"](message=analysis.raw_message, meds=context.meds, **common)
    if current_intent == "observation_check":
        return ops["answer_observation_check_intent"](
            message=analysis.raw_message,
            matched_med=analysis.target_med,
            **common,
        )
    if current_intent == "hospital_schedule":
        return ops["answer_hospital_schedule_intent"](
            hospital_schedules=context.hospital_schedules,
            message=analysis.raw_message,
            session_memory=context.session_memory,
            **common,
        )
    if current_intent == "general_caution":
        return ops["answer_general_caution_intent"](
            profile=context.profile,
            guide=context.latest_guide,
            meds=context.meds,
            schedules=context.schedules,
            adherence_summary=context.adherence_summary,
            **common,
        )
    if current_intent == "condition_general":
        return ops["answer_condition_general_intent"](
            condition_name=analysis.target_condition,
            meds=context.meds,
            schedules=context.schedules,
            profile=context.profile,
            message=analysis.raw_message,
            **common,
        )
    return None


async def build_deterministic_answer_parts(
    *,
    analysis: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> list[str]:
    deterministic_parts: list[str] = []

    for current_intent in analysis.intents:
        answer = _resolve_profile_deterministic_answer(
            current_intent=current_intent,
            analysis=analysis,
            context=context,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
            ops=ops,
        )
        if answer is None:
            answer = await _resolve_async_deterministic_answer(
                current_intent=current_intent,
                analysis=analysis,
                context=context,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
                ops=ops,
            )
        if answer is None:
            answer = _resolve_sync_deterministic_answer(
                current_intent=current_intent,
                analysis=analysis,
                context=context,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
                ops=ops,
            )
        if answer:
            deterministic_parts.append(answer)

    return deterministic_parts
