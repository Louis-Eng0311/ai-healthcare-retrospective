from __future__ import annotations

from typing import Any


def _build_condition_profile_points(*, profile: Any | None, condition: str, ops: dict[str, Any]) -> list[str]:
    if not profile:
        return []
    points: list[str] = []
    allergies = ops["split_text_items"](getattr(profile, "allergies", None))
    other_conditions = [item for item in ops["split_text_items"](getattr(profile, "conditions", None)) if item != condition]
    if allergies:
        points.append("알레르기: " + ", ".join(allergies[:2]))
    if other_conditions:
        points.append("함께 관리 중인 상태: " + ", ".join(other_conditions[:2]))
    return points


def _find_related_meds(*, meds: list[dict[str, Any]], related_keywords: list[str]) -> list[str]:
    related_meds: list[str] = []
    for med in meds:
        name = str(med.get("display_name") or "").strip()
        if name and any(keyword in name for keyword in related_keywords):
            related_meds.append(name)
    return related_meds


def _condition_lead(condition: str) -> str:
    lead_map = {
        "골다공증": "골다공증은 보통 칼슘·비타민D 보충과 함께 골흡수 억제제 같은 치료약을 사용합니다.",
        "고혈압": "고혈압은 혈압약을 꾸준히 복용하면서 어지러움이나 저혈압 증상을 함께 확인하는 것이 중요합니다.",
        "고지혈증": "고지혈증은 지질강하제 복용과 식습관, 운동 관리가 함께 중요합니다.",
        "빈혈": "빈혈은 원인에 따라 철분제나 원인 교정 치료를 함께 보는 경우가 많습니다.",
    }
    if condition in {"당뇨", "제2형 당뇨"}:
        return "당뇨는 혈당 조절 약과 식사·운동 관리가 함께 가는 경우가 많습니다."
    return lead_map.get(condition, f"{condition}은 진단 상태와 현재 복용약을 함께 보고 치료 방향을 정하는 것이 중요합니다.")


def _classify_related_schedule_groups(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    related_keywords: list[str],
    ops: dict[str, Any],
) -> tuple[list[str], list[str]]:
    med_id_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
    daily: list[str] = []
    weekly: list[str] = []
    for schedule in schedules:
        patient_med_id = schedule.get("patient_med_id")
        if patient_med_id is None:
            continue
        med = med_id_map.get(int(patient_med_id))
        if not med:
            continue
        name = str(med.get("display_name") or "").strip()
        if not any(keyword in name for keyword in related_keywords):
            continue
        times = schedule.get("times") or []
        for item in times:
            days = str(item.get("days_of_week") or "").strip().upper()
            if days in {"SAT", "SUN", "MON"} and len(times) == 1 and ("알렌드론" in name or "리세드론" in name):
                weekly.append(name)
            elif "MON,TUE,WED,THU,FRI,SAT,SUN" in days or ops["humanize_days"](days) == "매일":
                daily.append(name)
    return ops["dedupe_lines"](daily, limit=3), ops["dedupe_lines"](weekly, limit=3)


def _build_related_schedule_summary(*, daily: list[str], weekly: list[str]) -> str | None:
    if not daily and not weekly:
        return None
    parts: list[str] = []
    if daily:
        parts.append("매일 챙길 약: " + ", ".join(daily))
    if weekly:
        parts.append("주 1회 확인할 약: " + ", ".join(weekly))
    return " / ".join(parts)


def answer_condition_general_intent(
    *,
    condition_name: str | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    profile: Any | None,
    message: str,
    target_label: str,
    requester_role: Any,
    audience: str,
    condition_med_keywords: dict[str, list[str]],
    ops: dict[str, Any],
) -> str:
    condition = str(condition_name or "해당 질환").strip()
    profile_points = _build_condition_profile_points(profile=profile, condition=condition, ops=ops)
    related_keywords = condition_med_keywords.get(condition, [])
    related_meds = _find_related_meds(meds=meds, related_keywords=related_keywords)

    lines = [_condition_lead(condition)]
    if related_meds:
        related_text = ", ".join(ops["dedupe_lines"](related_meds, limit=3))
        lines.append(f"현재 기록에서는 {ops['with_particle'](related_text, ('이', '가'))} 관련 약으로 보입니다.")
        if ops["contains_any"](message, ["매일", "주 1회", "나눠", "구분"]) and schedules:
            daily, weekly = _classify_related_schedule_groups(
                meds=meds,
                schedules=schedules,
                related_keywords=related_keywords,
                ops=ops,
            )
            summary = _build_related_schedule_summary(daily=daily, weekly=weekly)
            if summary:
                lines.append(summary)

    if profile_points:
        lines.append("현재 기록 기준으로는 " + " / ".join(profile_points[:2]) + "도 함께 확인하는 것이 좋습니다.")
    lines.append("새 약을 추가하거나 바꾸는 판단은 현재 복용약과 병력 확인 후 의료진과 상의하는 것이 안전합니다.")

    base = " ".join(lines)
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def build_interaction_focus_points(
    *, med_names: list[str], adherence_summary: dict[str, Any] | None, ops: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if med_names:
        record_points.append("현재 확인되는 복용약은 " + ", ".join(ops["dedupe_lines"](med_names, limit=4)) + "입니다.")
    if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
        missed_names = adherence_summary.get("recent_missed_names") or []
        if missed_names:
            record_points.append("최근 놓친 기록이 있는 약은 " + ", ".join(ops["dedupe_lines"](missed_names, limit=3)) + "입니다.")

    flags_by_med = {name: ops["med_category_flags"](name) for name in med_names}
    nsaid_meds = [name for name, flags in flags_by_med.items() if "nsaid" in flags]
    acet_meds = [name for name, flags in flags_by_med.items() if "acetaminophen" in flags]
    antihistamine_meds = [name for name, flags in flags_by_med.items() if "antihistamine" in flags]

    if len(nsaid_meds) >= 2:
        general_points.append("진통소염제 계열이 겹칠 수 있어 위장 증상, 신장 부담, 출혈 위험을 특히 조심해 보는 것이 좋습니다.")
    if nsaid_meds and acet_meds:
        general_points.append("해열진통제와 소염진통제를 함께 쓰는 형태일 수 있어 추가 복용을 임의로 늘리지 않는 것이 좋습니다.")
    if len(antihistamine_meds) >= 2:
        general_points.append("항히스타민 계열이 겹치면 졸림이나 집중력 저하를 더 주의해서 보는 것이 좋습니다.")
    if not general_points:
        general_points.append("현재 약 이름만으로 중대한 상호작용을 단정하긴 어렵지만, 성분 중복 여부를 먼저 확인하는 것이 안전합니다.")

    next_points.append("처방 외 진통제나 감기약을 추가할 때는 성분표와 현재 복용약 이름을 같이 확인해 주세요.")
    if adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0:
        next_points.append("상호작용 확인과 함께 복약 누락이 반복되지 않는지도 같이 보는 것이 좋습니다.")
    return record_points, general_points, next_points


def _build_external_overlap_points(
    *,
    external_drug_name: str,
    med_names: list[str],
    ops: dict[str, Any],
) -> list[str]:
    points: list[str] = []
    external_flags = ops["med_category_flags"](external_drug_name)
    current_flags = {name: ops["med_category_flags"](name) for name in med_names}
    overlapping_nsaids = [name for name, flags in current_flags.items() if "nsaid" in flags and "nsaid" in external_flags]
    overlapping_ace = [name for name, flags in current_flags.items() if "acetaminophen" in flags and "acetaminophen" in external_flags]
    overlapping_antihistamine = [name for name, flags in current_flags.items() if "antihistamine" in flags and "antihistamine" in external_flags]

    if overlapping_nsaids:
        points.append(f"{external_drug_name}은 진통소염제 계열로 보이며 현재 복용약 중 {', '.join(overlapping_nsaids[:3])}과 계열이 겹칠 수 있습니다.")
    if overlapping_ace:
        points.append(f"{external_drug_name}은 아세트아미노펜 계열로 보이며 현재 복용약 중 {', '.join(overlapping_ace[:3])}과 중복 여부를 먼저 확인하는 것이 좋습니다.")
    if overlapping_antihistamine:
        points.append(f"{external_drug_name}은 항히스타민 계열로 보이며 현재 복용약 중 {', '.join(overlapping_antihistamine[:3])}과 함께 복용 시 졸림을 더 주의해서 볼 수 있습니다.")
    return points


def _append_profile_record_points(*, profile: Any | None, record_points: list[str], ops: dict[str, Any]) -> None:
    if not profile:
        return
    allergies = ops["split_text_items"](getattr(profile, "allergies", None))
    conditions = ops["split_text_items"](getattr(profile, "conditions", None))
    if allergies:
        record_points.append("등록된 알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
    if conditions:
        record_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")


def _append_lookup_general_points(*, external_drug_name: str, lookup: dict[str, Any] | None, general_points: list[str], ops: dict[str, Any]) -> None:
    if not lookup:
        return
    mfds_item = lookup.get("mfds")
    kids_items = lookup.get("kids") or []
    efficacy = ops["summarize_text"](getattr(mfds_item, "efficacy", None), max_sentences=1) if mfds_item else ""
    precautions = ops["summarize_text"](getattr(mfds_item, "precautions", None), max_sentences=1) if mfds_item else ""
    if efficacy:
        general_points.append(f"{external_drug_name}은 일반적으로 {efficacy}")
    if precautions:
        general_points.append(f"주의사항으로는 {precautions}")
    if kids_items:
        kids_summary = ops["summarize_text"](kids_items[0].get("content"), max_sentences=1)
        if kids_summary:
            general_points.append(f"추가 안전 근거로는 {kids_summary}")


def _append_adherence_points(
    *,
    adherence_summary: dict[str, Any] | None,
    record_points: list[str],
    next_points: list[str],
    ops: dict[str, Any],
) -> None:
    if not (adherence_summary and int(adherence_summary.get("missed", 0) or 0) > 0):
        return
    missed_names = ops["dedupe_lines"](
        [str(name).strip() for name in (adherence_summary.get("recent_missed_names") or []) if str(name).strip()],
        limit=2,
    )
    if missed_names:
        record_points.append("최근 복용을 놓친 약은 " + ", ".join(missed_names) + "입니다.")
    next_points.append("새 약 비교와 함께 최근 놓친 약이 있다면 복용 간격이 겹치지 않는지도 같이 확인해 주세요.")


def build_external_interaction_points(
    *,
    external_drug_name: str,
    meds: list[dict[str, Any]],
    profile: Any | None,
    adherence_summary: dict[str, Any] | None,
    lookup: dict[str, Any] | None,
    ops: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    med_names = [str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()]
    record_points: list[str] = [f"현재 복용약은 {', '.join(ops['dedupe_lines'](med_names, limit=4))}입니다."] if med_names else []
    general_points = _build_external_overlap_points(
        external_drug_name=external_drug_name,
        med_names=med_names,
        ops=ops,
    )
    next_points: list[str] = []

    _append_profile_record_points(profile=profile, record_points=record_points, ops=ops)
    if not general_points:
        general_points.append(f"{external_drug_name}을 현재 약과 같이 복용해도 되는지 판단하려면 성분 중복과 진통제/감기약 계열 중복 여부를 먼저 확인하는 것이 좋습니다.")
    _append_lookup_general_points(external_drug_name=external_drug_name, lookup=lookup, general_points=general_points, ops=ops)
    _append_adherence_points(
        adherence_summary=adherence_summary,
        record_points=record_points,
        next_points=next_points,
        ops=ops,
    )

    next_points.append("새 약을 추가하기 전에는 제품명뿐 아니라 성분명도 함께 확인해 주세요.")
    next_points.append("복용 후 발진, 호흡 불편, 심한 어지러움이 있으면 추가 복용 전에 상태를 다시 확인하는 것이 좋습니다.")
    return record_points, general_points, next_points
