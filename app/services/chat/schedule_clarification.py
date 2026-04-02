from __future__ import annotations

from typing import Any


def answer_hospital_schedule_intent(
    *,
    hospital_schedules: list[Any],
    message: str,
    session_memory: Any | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    if not hospital_schedules:
        base = f"{target_label} 기준으로 등록된 병원 예약이나 검사 일정이 없습니다."
        return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

    normalized = (message or "").strip()
    upcoming = [item for item in hospital_schedules if getattr(item, "scheduled_at", None) is not None]
    focus = str(getattr(session_memory, "recent_hospital_focus", "") or "").strip()

    filtered = upcoming or hospital_schedules
    if ops["contains_any"](normalized, ["외래", "진료"]) or "외래/진료" in focus:
        filtered = [item for item in filtered if ops["contains_any"](str(getattr(item, "title", "") or ""), ["외래", "진료"])] or filtered
    elif ops["contains_any"](normalized, ["검사"]) or "검사" in focus:
        filtered = [item for item in filtered if ops["contains_any"](str(getattr(item, "title", "") or ""), ["검사"])] or filtered

    schedule_index = 0
    if ops["contains_any"](normalized, ["그 다음", "다다음"]) or normalized in ops["affirmative_short_replies"]:
        schedule_index = 1

    target_schedules = filtered or hospital_schedules
    has_followup_request = schedule_index == 1
    if has_followup_request and len(target_schedules) <= 1:
        title_hint = (
            "외래/진료 일정"
            if (ops["contains_any"](normalized, ["외래", "진료"]) or "외래/진료" in focus)
            else ("검사 일정" if (ops["contains_any"](normalized, ["검사"]) or "검사" in focus) else "병원 일정")
        )
        first_schedule = target_schedules[0]
        first_title = str(getattr(first_schedule, "title", "") or "병원 일정").strip()
        first_time = ops["format_datetime_korean"](getattr(first_schedule, "scheduled_at", None))
        base = (
            f"{target_label} 기준 그 다음 {title_hint}은 아직 등록되어 있지 않습니다.\n"
            f"현재 확인되는 가장 가까운 일정은 {first_time}의 {first_title}입니다."
        )
        hospital_name = str(getattr(first_schedule, "hospital_name", "") or "").strip()
        location = str(getattr(first_schedule, "location", "") or "").strip()
        if hospital_name:
            base += f"\n병원: {hospital_name}"
        if location:
            base += f"\n장소: {location}"
        return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

    target_schedule = target_schedules[schedule_index] if len(target_schedules) > schedule_index else target_schedules[0]
    if ops["contains_any"](normalized, ["언제", "다음", "가장 가까운", "최근", "예약 언제였지"]):
        title = str(getattr(target_schedule, "title", "") or "병원 일정").strip()
        hospital_name = str(getattr(target_schedule, "hospital_name", "") or "").strip()
        location = str(getattr(target_schedule, "location", "") or "").strip()
        scheduled_at = ops["format_datetime_korean"](getattr(target_schedule, "scheduled_at", None))
        parts = [
            (
                f"{target_label} 기준 그 다음 병원 일정은 {scheduled_at}의 {title}입니다."
                if schedule_index == 1 and len(target_schedules) > 1
                else f"{target_label} 기준 가장 가까운 병원 일정은 {scheduled_at}의 {title}입니다."
            )
        ]
        if hospital_name:
            parts.append(f"병원: {hospital_name}")
        if location:
            parts.append(f"장소: {location}")
        base = "\n".join(parts)
    else:
        base = f"{target_label} 기준 등록된 병원 일정은 다음과 같습니다.\n{ops['build_hospital_schedule_text'](hospital_schedules[:3])}"

    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def build_clarification_reply(
    *,
    analysis: Any,
    context: Any,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    message = ops["normalize_user_message"](analysis.raw_message)

    if analysis.primary_intent == "general":
        if ops["contains_any"](message, ["예약", "병원", "외래", "검사", "진료"]):
            if context.hospital_schedules:
                return ops["answer_hospital_schedule_intent"](
                    hospital_schedules=context.hospital_schedules,
                    message=message,
                    session_memory=context.session_memory,
                    target_label=target_label,
                    requester_role=requester_role,
                    audience=audience,
                )
            base = (
                f"{target_label} 기준으로 병원 일정 질문으로 보입니다. "
                "외래 예약인지, 검사 일정인지, 가장 가까운 방문 일정인지 한 가지로 적어 주시면 바로 확인해 드리겠습니다."
            )
            return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

        if ops["contains_any"](message, ["같이 먹", "같이 복용", "조합", "상호작용"]):
            base = (
                "현재 복용약끼리 비교할지, 새로 받은 약까지 포함할지 먼저 알려 주세요. "
                "약 이름이 있으면 주의 조합을 바로 정리해 드릴 수 있습니다."
            )
            return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

        if ops["contains_any"](message, ops["followup_med_references"]):
            base = (
                "약 이름만 괄호로 다시 보내 주세요. 예: (푸마티펜정케토티펜)\n"
                "이렇게 보내 주시면 그 약 기준으로 복용 시간이나 설명을 바로 이어서 안내해 드리겠습니다."
            )
            return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

    if analysis.primary_intent == "medication_caution" and not analysis.target_med and not analysis.external_drug_name:
        if context.meds:
            return ops["answer_drug_interaction_overview"](
                meds=context.meds,
                adherence_summary=context.adherence_summary,
                target_label=target_label,
                requester_role=requester_role,
                audience=audience,
            )
        base = "상호작용을 보려면 비교할 약 이름이 필요합니다. 현재 복용약끼리 볼지, 특정 약을 새로 추가해 볼지 알려 주세요."
        return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base

    return None


def answer_general_caution_intent(
    *,
    profile: Any | None,
    guide: Any | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    points: list[str] = []

    if profile:
        allergies = ops["split_text_items"](getattr(profile, "allergies", None))
        conditions = ops["split_text_items"](getattr(profile, "conditions", None))
        if allergies:
            points.append("알레르기: " + ", ".join(allergies))
        if conditions:
            points.append("건강 상태: " + ", ".join(conditions))
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        if sleep_hours is not None:
            points.append(f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있어, 수면 리듬을 일정하게 유지하는 것이 좋습니다.")
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        if exercise_minutes is not None:
            points.append(f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있어 무리하지 않는 범위에서 꾸준히 유지하는 것이 좋습니다.")

    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if ("주의" in title or "생활" in title) and body:
                first_line = body.splitlines()[0].strip().lstrip("-").strip()
                if first_line and first_line not in points:
                    points.append(first_line)
            if len(points) >= 3:
                break

    if not points and meds:
        for med in meds[:2]:
            med_name = str(med.get("display_name") or "").strip()
            med_notes = str(med.get("notes") or "").strip()
            if med_name and med_notes:
                points.append(f"{med_name}: {med_notes}")

    if not points and schedules:
        schedule_text = ops["build_schedule_text"](schedules, meds)
        first_line = ops["first_clean_line"](schedule_text)
        if first_line and first_line != "등록된 복약 일정 없음":
            points.append(f"복약 일정: {first_line}")

    points.extend(ops["build_adherence_guidance_points"](adherence_summary=adherence_summary))
    if not points:
        return None

    base = f"{target_label} 기준으로 지금 특히 주의해서 볼 점은 다음과 같습니다.\n" + "\n".join(
        f"- {point}" for point in ops["dedupe_lines"](points, limit=3)
    )
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
