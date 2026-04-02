from __future__ import annotations

from typing import Any


async def build_patient_chat_context(
    *,
    session_id: int,
    patient_id: int,
    include_kids_evidence: bool,
    chat_history_turns: int,
    slow_context_seconds: float,
    context_factory: Any,
    logger: Any,
    log_metric: Any,
    now_counter: Any,
    ops: dict[str, Any],
) -> Any:
    started = now_counter()
    (
        profile,
        latest_guide,
        meds,
        schedules,
        hospital_schedules,
        dur_alerts,
        session_memory,
        recent_messages,
    ) = await ops["gather"](
        ops["get_profile"](patient_id),
        ops["get_latest_done_guide"](patient_id),
        ops["get_active_meds"](patient_id),
        ops["get_active_schedules"](patient_id),
        ops["get_hospital_schedules"](patient_id),
        ops["get_active_dur_alerts"](patient_id),
        ops["get_session_memory"](session_id),
        ops["chat_message_model"].filter(session_id=session_id).order_by("-created_at", "-id").limit(chat_history_turns).all(),
    )
    adherence_summary = await ops["get_recent_adherence_summary"](
        patient_id=patient_id,
        meds=meds,
        format_datetime=ops["format_datetime_korean"],
    )
    recent_messages = list(reversed(recent_messages))
    kids_evidence = await ops["build_kids_evidence"](meds=meds) if include_kids_evidence else []
    rag_context: list[dict[str, Any]] = []

    elapsed = now_counter() - started
    elapsed_ms = int(elapsed * 1000)
    if elapsed >= slow_context_seconds:
        logger.warning(
            "chat context slow session_id=%s patient_id=%s elapsed_ms=%s meds=%s schedules=%s",
            session_id,
            patient_id,
            elapsed_ms,
            len(meds),
            len(schedules),
        )
    log_metric(
        "context_build",
        session_id=session_id,
        patient_id=patient_id,
        elapsed_ms=elapsed_ms,
        meds=len(meds),
        schedules=len(schedules),
        dur_alerts=len(dur_alerts),
    )

    return context_factory(
        patient_id=patient_id,
        profile=profile,
        latest_guide=latest_guide,
        meds=meds,
        schedules=schedules,
        hospital_schedules=hospital_schedules,
        dur_alerts=dur_alerts,
        adherence_summary=adherence_summary,
        recent_messages=recent_messages,
        session_memory=session_memory,
        kids_evidence=kids_evidence,
        rag_context=rag_context,
    )
