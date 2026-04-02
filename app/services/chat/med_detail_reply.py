from __future__ import annotations

from typing import Any


async def answer_med_detail_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[Any] | None,
    session_memory: Any | None = None,
    matched_med: dict[str, Any] | None = None,
    dur_alerts: list[dict[str, Any]] | None = None,
    adherence_summary: dict[str, Any] | None = None,
    guide: Any | None = None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    matched = matched_med or ops["extract_target_med"](
        message=message,
        meds=meds,
        recent_messages=recent_messages,
        session_memory=session_memory,
    )
    if not matched:
        return None

    name = str(matched.get("display_name") or "해당 약").strip()
    dosage = str(matched.get("dosage") or "").strip()
    notes = str(matched.get("notes") or "").strip()
    patient_med_id = matched.get("patient_med_id")

    schedule_lines: list[str] = []
    for schedule in schedules:
        if schedule.get("patient_med_id") != patient_med_id:
            continue
        for item in schedule.get("times") or []:
            time_label = ops["humanize_time"](item.get("time_of_day"))
            days_label = ops["humanize_days"](item.get("days_of_week"))
            schedule_lines.append(f"{days_label} {time_label}".strip())

    lookup = await ops["lookup_external_med_info"](name)
    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []
    med_info = matched.get("drug_info") or {}
    catalog_info = matched.get("drug_catalog") or {}

    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    efficacy = ops["first_clean_line"](getattr(mfds_item, "efficacy", None)) if mfds_item else ""
    if not efficacy:
        efficacy = ops["summarize_text"](med_info.get("efficacy"), max_sentences=1)
    if dosage:
        record_points.append(f"{name} 용량은 {dosage}로 기록되어 있습니다.")
    if efficacy:
        general_points.append(f"{name}은 보통 {efficacy}")
    if schedule_lines:
        record_points.append("복용 시간은 " + ", ".join(schedule_lines[:3]) + "입니다.")
    if notes:
        record_points.append(f"복용 메모에는 `{notes}`로 남아 있습니다.")
    precautions = ops["summarize_text"](getattr(mfds_item, "precautions", None), max_sentences=1) if mfds_item else ""
    if not precautions:
        precautions = ops["summarize_text"](med_info.get("precautions"), max_sentences=1)
    if precautions:
        general_points.append(f"주의사항으로는 {precautions}")
    if med_info.get("storage_method"):
        general_points.append(f"보관 방법은 {ops['first_clean_line'](str(med_info.get('storage_method') or ''))}")
    ingredients = ops["first_clean_line"](str(catalog_info.get("ingredients") or ""))
    if ingredients:
        general_points.append(f"성분 참고로는 {ingredients}")
    if kids_items:
        kids_summary = ops["first_clean_line"](kids_items[0].get("content"))
        if kids_summary:
            general_points.append(f"추가 안전 근거로는 {kids_summary}")
    dur_points = ops["extract_dur_alert_points"](dur_alerts=dur_alerts or [], med_name=name, limit=2)
    if dur_points:
        next_points.extend(dur_points)
    med_adherence_points = ops["build_med_adherence_points"](med_name=name, adherence_summary=adherence_summary)
    if med_adherence_points:
        record_points.extend(med_adherence_points)
    guide_points = ops["build_med_guidance_points"](guide=guide, med_name=name)
    if guide_points:
        next_points.extend(guide_points[:2])
    if not next_points:
        next_points.append("복용 시간과 추가 복용 여부를 임의로 바꾸기보다 현재 일정과 처방 지시를 먼저 확인해 주세요.")

    base = ops["compose_medical_sections"](
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return (
        ops["to_caregiver_style"](answer=base, audience=audience)
        if requester_role == ops["caregiver_role"]
        else base
    )
