from __future__ import annotations

from typing import Any


def answer_profile_intent(
    *,
    intent: str,
    profile: Any | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str | None:
    if not profile:
        base = f"{target_label} 기준으로 등록된 건강 프로필이 없습니다."
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_smoking":
        smoker = getattr(profile, "is_smoker", None)
        value = getattr(profile, "avg_cig_packs_per_week", None)
        if value is None and smoker is None:
            base = f"{target_label} 기준으로 흡연 정보가 등록되어 있지 않습니다."
        elif value is None and smoker is False:
            base = f"{target_label} 기준으로 비흡연으로 기록되어 있습니다."
        elif value is None:
            base = f"{target_label} 기준으로 흡연 중으로 보이지만 주간 흡연량은 등록되어 있지 않습니다."
        else:
            prefix = "흡연 중이며 " if smoker is not False else "현재 비흡연으로 기록되어 있으나, "
            base = f"{target_label} 기준으로 {prefix}주에 평균 {value}갑 정도 흡연하는 것으로 기록되어 있습니다."
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_alcohol":
        value = getattr(profile, "avg_alcohol_bottles_per_week", None)
        if value is None:
            base = f"{target_label} 기준으로 주간 음주량 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 주에 평균 {value}병 정도 음주하는 것으로 기록되어 있습니다."
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_sleep":
        value = getattr(profile, "avg_sleep_hours_per_day", None)
        if value is None:
            base = f"{target_label} 기준으로 평균 수면 시간 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 하루 평균 {value}시간 정도 수면하는 것으로 기록되어 있습니다."
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_exercise":
        value = getattr(profile, "avg_exercise_minutes_per_day", None)
        if value is None:
            base = f"{target_label} 기준으로 평균 운동 시간 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준으로 하루 평균 {value}분 정도 운동하는 것으로 기록되어 있습니다."
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_body":
        height_cm = getattr(profile, "height_cm", None)
        weight_kg = getattr(profile, "weight_kg", None)
        bmi = getattr(profile, "bmi", None)
        points: list[str] = []
        if height_cm is not None:
            points.append(f"키는 {height_cm}cm입니다.")
        if weight_kg is not None:
            points.append(f"몸무게는 {weight_kg}kg입니다.")
        if bmi is not None:
            bmi_category = ops["bmi_category_text"](bmi)
            if bmi_category:
                points.append(f"BMI는 {bmi}이며 {bmi_category}입니다.")
            else:
                points.append(f"BMI는 {bmi}입니다.")
        if not points:
            base = f"{target_label} 기준으로 키, 몸무게, BMI 정보가 등록되어 있지 않습니다."
        else:
            base = f"{target_label} 기준 건강 프로필 수치는 다음과 같습니다.\n" + "\n".join(
                f"- {point}" for point in points
            )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_summary":
        lines = ops["build_profile_summary_lines"](profile)
        if not lines:
            base = f"{target_label} 기준으로 요약할 건강 프로필 정보가 아직 충분하지 않습니다."
        else:
            base = f"{target_label} 기준 건강 프로필을 요약하면 다음과 같습니다.\n" + "\n".join(
                f"- {line}" for line in lines[:6]
            )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_conditions":
        conditions = ops["split_text_items"](getattr(profile, "conditions", None))
        if not conditions:
            base = f"{target_label} 기준으로 등록된 기저질환이나 건강 상태 정보가 없습니다."
        else:
            base = f"{target_label} 기준 건강 상태는 다음과 같이 기록되어 있습니다.\n" + "\n".join(
                f"- {condition}" for condition in conditions[:5]
            )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_allergies":
        allergies = ops["split_text_items"](getattr(profile, "allergies", None))
        if not allergies:
            base = f"{target_label} 기준으로 등록된 알레르기 정보가 없습니다."
        else:
            base = f"{target_label} 기준 알레르기 정보는 다음과 같습니다.\n" + "\n".join(
                f"- {allergy}" for allergy in allergies[:5]
            )
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    if intent == "profile_hospitalization":
        is_hospitalized = getattr(profile, "is_hospitalized", None)
        discharge_date = getattr(profile, "discharge_date", None)
        if is_hospitalized is None and discharge_date is None:
            base = f"{target_label} 기준으로 입원/퇴원 정보가 등록되어 있지 않습니다."
        elif is_hospitalized is True:
            base = f"{target_label} 기준으로 현재 입원 중으로 기록되어 있습니다."
            if discharge_date:
                base += f"\n- 퇴원 예정 또는 기록된 퇴원일: {discharge_date}"
        else:
            base = f"{target_label} 기준으로 현재 입원 중은 아닌 것으로 기록되어 있습니다."
            if discharge_date:
                base += f"\n- 기록된 퇴원일: {discharge_date}"
        return (
            ops["to_caregiver_style"](answer=base, audience=audience)
            if requester_role == ops["caregiver_role"]
            else base
        )

    return None
