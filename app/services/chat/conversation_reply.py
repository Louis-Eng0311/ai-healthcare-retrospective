from __future__ import annotations

from typing import Any


def answer_med_time_split_intent(
    *,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    med_name_map = {int(med.get("patient_med_id")): med for med in meds if med.get("patient_med_id") is not None}
    morning: list[str] = []
    evening: list[str] = []
    other: list[str] = []

    for schedule in schedules:
        patient_med_id = int(schedule.get("patient_med_id"))
        med = med_name_map.get(patient_med_id, {})
        label = med.get("display_name") or f"약 #{patient_med_id}"
        dosage = med.get("dosage")
        notes = str(med.get("notes") or "").strip()
        shown = f"{label} {dosage}".strip()
        if any(keyword in notes for keyword in ["필요", "열날", "증상", "통증 시"]):
            other.append(f"{shown} (필요 시 복용)")
            continue
        times = schedule.get("times") or []
        if not times:
            other.append(shown)
            continue
        for item in times:
            time_of_day = str(item.get("time_of_day") or "")
            hour = int(time_of_day.split(":")[0]) if ":" in time_of_day else -1
            if 4 <= hour < 12:
                morning.append(shown)
            elif 17 <= hour <= 23:
                evening.append(shown)
            else:
                other.append(f"{shown} ({ops['humanize_time'](time_of_day)})")

    parts = [f"{target_label} 기준으로 복약 시간을 나누면 다음과 같습니다."]
    if morning:
        parts.append("아침:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(morning)))
    if evening:
        parts.append("저녁:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(evening)))
    if other:
        parts.append("기타 시간:")
        parts.extend(f"- {item}" for item in list(dict.fromkeys(other)))
    if len(parts) == 1:
        parts.append("- 등록된 복약 일정 정보가 충분하지 않습니다.")

    base = "\n".join(parts)
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def answer_session_summary_intent(
    *,
    meds: list[dict[str, Any]],
    profile: Any | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    med_names = [str(med.get("display_name")).strip() for med in meds if str(med.get("display_name") or "").strip()]
    conditions = ops["split_text_items"](getattr(profile, "conditions", None) if profile else None)
    allergies = ops["split_text_items"](getattr(profile, "allergies", None) if profile else None)
    current_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []

    if conditions:
        current_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
    if allergies:
        current_points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
    if med_names:
        current_points.append("현재 복약 관리는 " + ", ".join(ops["dedupe_lines"](med_names, limit=4)) + " 중심입니다.")
    else:
        current_points.append("현재 복용 약 정보는 아직 충분하지 않습니다.")

    general_points.append("기록된 건강 상태와 복약 일정, 최근 복약 흐름을 같이 보면서 관리 우선순위를 정리하는 것이 좋습니다.")
    if adherence_summary and int(adherence_summary.get("total", 0) or 0) > 0:
        taken = int(adherence_summary.get("taken", 0) or 0)
        missed = int(adherence_summary.get("missed", 0) or 0)
        pending = int(adherence_summary.get("pending", 0) or 0)
        current_points.append(f"최근 복약 기록은 완료 {taken}건, 놓침 {missed}건, 대기 {pending}건입니다.")
        if missed > 0:
            next_points.append("최근 놓친 약부터 오늘 일정에 다시 들어 있는지 먼저 확인하는 것이 좋습니다.")
        elif pending > 0:
            next_points.append("아직 복용 대기 상태인 일정이 남아 있는지 함께 확인하는 것이 좋습니다.")
    else:
        next_points.append("복약 기록이 충분하지 않다면 오늘 일정과 실제 복용 여부를 먼저 맞춰 보는 것이 좋습니다.")

    base = ops["compose_medical_sections"](
        current_record_points=current_points,
        general_info_points=general_points,
        next_check_points=next_points,
    )
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def answer_daily_chat(
    *,
    message: str,
    requester_role: Any,
    target_label: str,
    data_readiness: str = "partial",
    ops: dict[str, Any],
) -> str:
    normalized = (message or "").strip()

    if ops["contains_any"](normalized, ["이름이 뭐", "너 이름", "누구야"]):
        return "저는 복약과 건강 정보를 도와드리는 의료 챗봇입니다."
    if ops["contains_any"](normalized, ops["bot_capability_keywords"]):
        if data_readiness == "empty":
            return (
                "저는 약 정보, 복용 시 주의사항, 병원 일정, 건강프로필 입력 방법, 생활관리 질문을 도와드릴 수 있습니다. "
                "아직 기록이 적다면 일반적인 기준으로 먼저 설명드리고, 맞춤 답변이 필요한 경우에만 건강프로필이나 복약 정보를 더 요청드릴게요."
            )
        return (
            "저는 복용 중인 약, 복약 시간, 주의사항, 놓친 복약, 병원 일정, 건강프로필, 생활관리, 보호자 체크포인트를 "
            "안내해 드릴 수 있습니다. 기록이 부족한 부분은 일반적인 기준으로 먼저 설명드리고, 맞춤 답변이 필요할 때만 추가 정보를 부탁드립니다."
        )
    if ops["contains_any"](normalized, ["너 뭐해", "뭘 하는", "뭐 하는 애", "뭐하는 애", "뭐하는 애니"]):
        if data_readiness == "empty":
            return "저는 약 정보와 건강 질문을 기본적으로 안내하고, 기록이 쌓이면 복약 일정과 건강 기록까지 연결해 설명하는 의료 챗봇입니다."
        return "저는 복약 일정, 복용 중인 약, 주의사항, 건강 기록을 기준으로 안내를 도와드리는 의료 챗봇입니다."
    if ops["contains_any"](normalized, ["오늘 어때", "오늘 하루", "기분 어때"]):
        return "저는 괜찮습니다. 오늘도 복약과 건강 관련 질문을 도와드릴 준비가 되어 있습니다."
    if ops["contains_any"](normalized, ["고마워", "감사"]):
        return "도움이 되었다면 다행입니다. 필요한 내용이 있으면 이어서 말씀해 주세요."
    if ops["contains_any"](normalized, ["안녕", "반가워"]):
        if data_readiness == "empty":
            return (
                "안녕하세요. 복약과 건강 정보를 도와드릴게요. "
                "지금은 일반적인 약 정보나 건강 질문부터 안내드릴 수 있고, 건강프로필이나 복약 정보가 쌓이면 맞춤 답변까지 더 정확하게 이어드릴게요."
            )
        if data_readiness == "rich":
            return (
                f"안녕하세요. {target_label} 기준 기록을 참고해서 복약과 건강 정보를 도와드릴게요. "
                "약 정보, 복용 시간, 병원 일정, 건강프로필 중 궁금한 것을 편하게 물어보세요."
            )
        return (
            f"안녕하세요. {target_label} 기준으로 확인 가능한 기록을 참고해 복약과 건강 정보를 도와드릴게요. "
            "부족한 정보가 있으면 일반적인 기준으로 먼저 설명드리겠습니다."
        )
    if ops["contains_any"](normalized, ["잘 자"]):
        return "편안한 밤 보내세요. 복약 일정이 있다면 잊지 않도록 한 번 더 확인해 주세요."
    return (
        "일상적인 대화도 자연스럽게 이어갈 수 있습니다. 의료 관련 내용은 현재 기록이 있으면 맞춤형으로, 부족하면 일반적인 기준으로 먼저 안내드릴게요."
        if requester_role != ops["caregiver_role"]
        else "일상적인 대화도 가능하지만, 보호자 관점에서는 복약과 상태 확인 중심으로 우선 안내드릴 수 있습니다."
    )
