from __future__ import annotations

from typing import Any


async def answer_medication_caution_intent(
    *,
    message: str,
    guide: Any | None,
    meds: list[dict[str, Any]],
    profile: Any | None,
    dur_alerts: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    recent_messages: list[Any] | None,
    matched_med: dict[str, Any] | None,
    external_drug_name: str | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    interaction_drug_name = external_drug_name or ops["extract_external_drug_name"](message, recent_messages)
    if interaction_drug_name:
        return await ops["answer_external_interaction_intent"](
            external_drug_name=interaction_drug_name,
            meds=meds,
            profile=profile,
            adherence_summary=adherence_summary,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )

    if ops["contains_any"](message, ["새 감기약", "새 약", "감기약 추가", "감기약"]) and meds:
        record_points, general_points, next_points = ops["build_interaction_focus_points"](
            med_names=[
                str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()
            ],
            adherence_summary=adherence_summary,
        )
        general_points.insert(
            0,
            "새 감기약을 추가할 때는 해열진통제, 항히스타민, 진해거담 성분이 현재 복용약과 겹치지 않는지 먼저 확인하는 것이 좋습니다.",
        )
        base = ops["compose_medical_sections"](
            current_record_points=record_points,
            general_info_points=general_points,
            next_check_points=next_points
            or ["새로 추가할 감기약의 제품명이나 성분명을 알려 주시면 현재 약과 비교해 드릴 수 있습니다."],
        )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    matched_med = matched_med or ops["extract_target_med"](message=message, meds=meds, recent_messages=recent_messages)
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if matched_med:
        med_name = str(matched_med.get("display_name") or "해당 약").strip()
        med_notes = str(matched_med.get("notes") or "").strip()
        med_info = matched_med.get("drug_info") or {}
        if med_notes:
            record_points.append(f"{med_name} 메모에는 `{med_notes}`로 기록되어 있습니다.")
        lookup = await ops["lookup_external_med_info"](med_name)
        mfds_item = lookup.get("mfds")
        kids_items = lookup.get("kids") or []
        precautions = ops["first_clean_line"](getattr(mfds_item, "precautions", None)) if mfds_item else ""
        if not precautions:
            precautions = ops["first_clean_line"](str(med_info.get("precautions") or ""))
        if precautions:
            general_points.append(f"{med_name} 주의사항으로는 {precautions}")
        if "같이" in message or "상호작용" in message or "조심" in message:
            next_points.append(f"{med_name} 복용 후 두통, 발진, 호흡 불편 같은 이상 반응이 있으면 추가 복용 전에 상태를 확인해 주세요.")
        if kids_items:
            kids_summary = ops["first_clean_line"](kids_items[0].get("content"))
            if kids_summary:
                general_points.append(f"추가 안전 근거로는 {kids_summary}")
        next_points.extend(ops["extract_dur_alert_points"](dur_alerts=dur_alerts, med_name=med_name, limit=2))

    if profile and getattr(profile, "allergies", None):
        raw_allergies = str(profile.allergies).strip()
        if raw_allergies and ("음식" in message or "알레르기" in message):
            record_points.append(f"등록된 알레르기 정보는 {raw_allergies}입니다.")

    caution_body = ""
    if guide and isinstance(guide.content_json, dict):
        sections = guide.content_json.get("sections") or []
        for section in sections:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "")
            if "주의" in title or "주의" in body or "신호" in title:
                caution_body = body
                break

    if caution_body:
        for line in caution_body.split("\n"):
            clean = line.strip().lstrip("-").strip()
            if clean and clean not in next_points and not any(keyword in clean for keyword in ["운동", "수면", "생활"]):
                next_points.append(clean)

    if not record_points and not general_points and not next_points:
        return None
    if not next_points:
        next_points.append("새 약을 추가하거나 함께 복용하기 전에는 현재 복용약과 성분 중복 여부를 먼저 확인해 주세요.")

    base = ops["compose_medical_sections"](
        current_record_points=record_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    if audience == "senior":
        base += "\n어지러움이 있으면 낙상 위험도 함께 조심해 주세요."
    return (
        ops["to_caregiver_style"](answer=base, audience=audience)
        if requester_role == ops["caregiver_role"]
        else base
    )


async def answer_external_med_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    recent_messages: list[Any] | None,
    profile: Any | None,
    external_drug_name: str | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    drug_name = external_drug_name or ops["extract_external_drug_name"](message, recent_messages)
    current_med_match = ops["find_best_med_match"](query=drug_name or message, meds=meds)
    if current_med_match:
        current_med_answer = await ops["answer_med_detail_intent"](
            message=str(drug_name or message),
            meds=meds,
            schedules=schedules,
            recent_messages=recent_messages,
            session_memory=None,
            matched_med=current_med_match,
            adherence_summary=None,
            target_label=target_label,
            requester_role=requester_role,
            audience=audience,
        )
        if current_med_answer:
            return current_med_answer

    if not drug_name:
        base = (
            f"{target_label} 기준 현재 기록에 없는 약에 대해선 복용 여부를 바로 단정하기 어렵습니다. "
            "약 이름이나 처방 상황을 조금 더 알려주시면 확인 범위를 안내드릴 수 있습니다."
        )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    topic_particle = ops["choose_korean_particle"](drug_name, ("은", "는"))
    lookup = await ops["lookup_external_med_info"](drug_name)
    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []

    profile_points: list[str] = []
    if profile:
        allergies = ops["split_text_items"](getattr(profile, "allergies", None))
        conditions = ops["split_text_items"](getattr(profile, "conditions", None))
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        if allergies:
            profile_points.append("알레르기: " + ", ".join(allergies[:3]))
        if conditions:
            profile_points.append("건강 상태: " + ", ".join(conditions[:3]))
        if sleep_hours is not None:
            profile_points.append(f"수면: 하루 평균 {sleep_hours}시간")
        if exercise_minutes is not None:
            profile_points.append(f"운동: 하루 평균 {exercise_minutes}분")

    if mfds_item:
        record_points = [f"{drug_name}{topic_particle} 현재 복용 중인 약으로 기록되어 있지는 않습니다."]
        general_points: list[str] = []
        next_points: list[str] = []
        item_name = str(getattr(mfds_item, "item_name", "") or drug_name).strip()
        efficacy = ops["summarize_text"](getattr(mfds_item, "efficacy", None), max_sentences=1)
        precautions = ops["summarize_text"](getattr(mfds_item, "precautions", None), max_sentences=2)
        dosage_info = ops["summarize_text"](getattr(mfds_item, "dosage_info", None), max_sentences=1)
        if item_name:
            general_points.append(f"약 정보명은 {item_name}입니다.")
        if efficacy:
            general_points.append(f"일반적으로는 {efficacy}")
        if precautions:
            general_points.append(f"주의할 점으로는 {precautions}")
        if dosage_info:
            next_points.append(f"복용 참고로는 {dosage_info}")
        if kids_items:
            first_kids = ops["summarize_text"](kids_items[0].get("content"), max_sentences=1)
            if first_kids:
                general_points.append(f"추가 안전 근거로는 {first_kids}")
        if profile_points:
            record_points.append("현재 건강기록 기준으로는 " + " / ".join(profile_points[:2]) + "를 함께 보는 것이 좋습니다.")
        next_points.append("실제 복용 전에는 처방 여부와 성분을 다시 확인하고, 복용 판단은 의료진이나 약사와 상의하는 것이 좋습니다.")
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

    base = ops["compose_medical_sections"](
        current_record_points=[
            f"{drug_name}{topic_particle} 현재 복용 중인 약으로 기록되어 있지는 않습니다.",
            *(
                [f"현재 건강기록 기준으로는 {' / '.join(profile_points[:2])}를 함께 볼 수 있습니다."]
                if profile_points
                else []
            ),
        ],
        general_info_points=[],
        next_check_points=["제품명이나 성분명이 더 정확하면 안내 범위를 더 좁힐 수 있습니다."],
    )
    return (
        ops["to_caregiver_style"](answer=base, audience=audience)
        if requester_role == ops["caregiver_role"]
        else base
    )


async def answer_external_interaction_intent(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: Any | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    lookup = await ops["lookup_external_med_info"](external_drug_name)
    record_points, general_points, next_points = ops["build_external_interaction_points"](
        external_drug_name=external_drug_name,
        meds=meds,
        profile=profile,
        adherence_summary=adherence_summary,
        lookup=lookup,
    )
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
