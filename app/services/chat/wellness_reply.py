from __future__ import annotations

from typing import Any


def answer_lifestyle_top_intent(
    *,
    guide: Any | None,
    profile: Any | None,
    adherence_summary: dict[str, Any] | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    record_points: list[str] = []
    general_points: list[str] = []
    next_points: list[str] = []
    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if "생활" in title or "주의" in title:
                for line in body.split("\n"):
                    clean = line.strip().replace("- ", "")
                    if clean:
                        general_points.append(clean)
    if not general_points and guide and guide.content_text:
        general_points.extend([line.strip() for line in guide.content_text.split(".") if line.strip()])

    if profile:
        sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
        exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
        allergies = ops["split_text_items"](getattr(profile, "allergies", None))
        smoker = getattr(profile, "is_smoker", None)
        alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)

        if allergies:
            record_points.append(f"알레르기 주의 정보는 {', '.join(allergies[:2])}입니다.")
        if sleep_hours is not None:
            record_points.append(f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있습니다.")
        if exercise_minutes is not None:
            record_points.append(f"운동은 하루 평균 {exercise_minutes}분 정도로 기록되어 있습니다.")
        if smoker is True:
            record_points.append("흡연 중으로 기록되어 있어 호흡기 증상이나 약 복용 시 주의점을 함께 보는 것이 좋습니다.")
        if alcohol is not None:
            record_points.append(f"주간 음주량은 {alcohol}병으로 기록되어 있습니다.")
        if sleep_hours is not None and float(sleep_hours) < 6:
            next_points.append("수면 시간이 짧은 편이라 먼저 수면 리듬과 최근 복용약 영향을 함께 보는 것이 좋습니다.")
        if exercise_minutes is not None and int(exercise_minutes) < 20:
            next_points.append("활동량이 적은 편이라 무리 없는 범위에서 가벼운 활동을 유지하는지 확인하는 것이 좋습니다.")

    next_points.extend(ops["build_adherence_guidance_points"](adherence_summary=adherence_summary))
    if not next_points:
        if profile and getattr(profile, "is_smoker", None) is True:
            next_points.append("생활관리에서는 흡연과 음주가 현재 증상이나 약 복용에 영향을 주지 않는지 먼저 같이 보는 것이 좋습니다.")
        elif profile and getattr(profile, "avg_sleep_hours_per_day", None) is not None:
            next_points.append("기록상 수면 시간은 유지되고 있어도 실제 피로감, 중간 각성, 복용 후 졸림 같은 체감 변화가 있는지 함께 확인하는 것이 좋습니다.")
        else:
            next_points.append("생활관리에서는 현재 복약 일정과 생활 습관이 서로 영향을 주는 부분부터 먼저 확인하는 것이 좋습니다.")

    if not record_points and not general_points and not next_points:
        base = f"{target_label} 기준 생활관리 요약 정보가 아직 충분하지 않습니다."
    else:
        base = ops["compose_medical_sections"](
            current_record_points=record_points,
            general_info_points=general_points,
            next_check_points=next_points,
        )
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def answer_symptom_cause_intent(
    *,
    message: str,
    meds: list[dict[str, Any]],
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    normalized = (message or "").strip()
    points: list[str] = []
    urgency_points: list[str] = []
    med_names = [str(med.get("display_name") or "").strip() for med in meds if str(med.get("display_name") or "").strip()]

    has_gi_symptom = ops["contains_any"](
        normalized,
        ["복통", "배 아", "배아", "속쓰림", "속 쓰림", "속이 쓰", "속이 안 좋", "속이 안좋", "메스껍", "울렁", "구역", "구토"],
    )
    if has_gi_symptom:
        points.append("물을 조금씩 자주 마시고, 자극적인 음식이나 과식은 잠시 피하는 것이 좋습니다.")
        points.append("언제부터 아픈지와 마지막 복용 약 시간이 언제였는지 같이 확인해 보세요.")
        if any("아세트아미노펜" in name for name in med_names):
            points.append("현재 기록에 삼남아세트아미노펜이 있어도, 복통 때문에 임의로 진통제를 더 추가하기 전에는 성분 중복을 먼저 확인하는 것이 안전합니다.")
        elif med_names:
            points.append("현재 복용 중인 약 외에 진통제나 감기약을 임의로 더 먹기 전에는 성분을 먼저 확인하는 것이 좋습니다.")
        urgency_points.append("통증이 점점 심해지거나, 계속 토하거나, 피가 섞이거나, 열이 함께 나면 바로 진료를 받는 것이 안전합니다.")

    if "어지러" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["암로디핀", "텔미사르탄", "비소프롤롤", "푸로세미드"]):
                points.append(f"{name}은 어지러움과 관련해 함께 확인해 볼 수 있는 약입니다.")
    if "식은땀" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["메트포르민", "글리메피리드"]):
                points.append(f"{name} 복용 중 식은땀이나 떨림이 있으면 저혈당 여부도 먼저 확인하는 것이 좋습니다.")
    if "멍" in normalized or "출혈" in normalized:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if any(keyword in name for keyword in ["아스피린", "클로피도그렐"]):
                points.append(f"{name}은 멍이나 출혈 경향과 함께 확인할 수 있는 약입니다.")

    if not points:
        base = f"{target_label} 기준으로 증상과 약의 관련성을 단정할 수는 없지만, 복용 중인 약과 증상이 시작된 시점을 함께 확인하는 것이 좋습니다."
    else:
        heading = (
            f"{target_label} 기준으로 현재 증상에서 먼저 확인할 점은 다음과 같습니다."
            if has_gi_symptom
            else f"{target_label} 기준으로 현재 증상과 관련해 먼저 확인해 볼 약은 다음과 같습니다."
        )
        base = heading + "\n" + "\n".join(f"- {point}" for point in ops["dedupe_lines"](points, limit=4))
        if urgency_points:
            base += "\n" + "\n".join(f"- {item}" for item in ops["dedupe_lines"](urgency_points, limit=2))
        else:
            base += "\n증상이 심해지거나 새로 시작된 경우에는 복용 시점과 함께 의료진에게 알려 주세요."

    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
