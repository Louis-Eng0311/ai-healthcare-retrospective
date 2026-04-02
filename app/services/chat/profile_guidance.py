from __future__ import annotations

from typing import Any

from app.services.chat.keywords import (
    _PROFILE_ALCOHOL_KEYWORDS,
    _PROFILE_EXERCISE_KEYWORDS,
    _PROFILE_SLEEP_KEYWORDS,
    _PROFILE_SMOKING_KEYWORDS,
)


def _build_sleep_points(*, sleep_hours: Any, points: list[str]) -> None:
    if sleep_hours is None:
        return
    if float(sleep_hours) < 6:
        points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간으로 짧은 편이라 수면 부족 원인을 먼저 점검하는 것이 좋습니다.")
    elif float(sleep_hours) > 9:
        points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간으로 긴 편이라 피로감이나 복용약 영향도 함께 확인해 볼 수 있습니다.")
    else:
        points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간입니다.")


def _build_exercise_points(*, exercise_minutes: Any, points: list[str]) -> None:
    if exercise_minutes is None:
        return
    if int(exercise_minutes) < 20:
        points.append(f"운동은 하루 평균 {exercise_minutes}분으로 적은 편이라 가벼운 활동량 유지 여부를 같이 보는 것이 좋습니다.")
    else:
        points.append(f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있습니다.")


def _build_smoking_points(*, smoker: Any, cig_packs: Any, points: list[str]) -> None:
    if smoker is True:
        if cig_packs is not None:
            points.append(f"흡연 중이며 주간 흡연량은 {cig_packs}갑으로 기록되어 있어 증상 변화나 약 복용 시 주의사항을 함께 확인하는 것이 좋습니다.")
        else:
            points.append("흡연 중으로 기록되어 있어 호흡기 증상이나 약물 주의사항을 함께 보는 것이 좋습니다.")
    elif smoker is False:
        points.append("흡연은 하지 않는 것으로 기록되어 있습니다.")


def _build_profile_snapshot_points(*, profile: Any, ops: dict[str, Any], points: list[str]) -> None:
    conditions = ops["split_text_items"](getattr(profile, "conditions", None))
    allergies = ops["split_text_items"](getattr(profile, "allergies", None))
    notes = ops["summarize_text"](getattr(profile, "notes", None), max_sentences=1)

    if conditions:
        points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
    if allergies:
        points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")

    if getattr(profile, "is_hospitalized", None) is True:
        discharge_date = getattr(profile, "discharge_date", None)
        if discharge_date:
            points.append(f"현재 입원/퇴원 정보도 중요합니다. 기록상 퇴원일은 {discharge_date}입니다.")
        else:
            points.append("현재 입원 중으로 기록되어 있어 병원 지시사항을 우선 확인하는 것이 좋습니다.")
    if notes:
        points.append("건강 메모: " + notes)


def _append_guide_points(*, guide: Any | None, ops: dict[str, Any], points: list[str]) -> None:
    if not (guide and isinstance(guide.content_json, dict)):
        return
    for section in guide.content_json.get("sections") or []:
        title = str(section.get("title") or "")
        body = str(section.get("body") or "").strip()
        if ("생활" in title or "주의" in title or "복약" in title) and body:
            first_line = ops["first_clean_line"](body)
            if first_line:
                points.append(first_line)
        if len(points) >= 8:
            break


def build_profile_guidance_points(*, profile: Any | None, guide: Any | None, ops: dict[str, Any]) -> list[str]:
    points: list[str] = []
    if profile:
        _build_sleep_points(sleep_hours=getattr(profile, "avg_sleep_hours_per_day", None), points=points)
        _build_exercise_points(exercise_minutes=getattr(profile, "avg_exercise_minutes_per_day", None), points=points)
        _build_smoking_points(
            smoker=getattr(profile, "is_smoker", None),
            cig_packs=getattr(profile, "avg_cig_packs_per_week", None),
            points=points,
        )
        alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)
        if alcohol is not None:
            points.append(f"주간 음주량은 {alcohol}병으로 기록되어 있어 복용 중 약과의 음주 주의가 필요한지 같이 확인할 수 있습니다.")
        _build_profile_snapshot_points(profile=profile, ops=ops, points=points)

    _append_guide_points(guide=guide, ops=ops, points=points)
    return ops["dedupe_lines"](points, limit=6)


def _build_current_points(*, normalized: str, profile: Any | None, ops: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    current_points: list[str] = []
    context: dict[str, Any] = {}
    if not profile:
        return current_points, context

    sleep_hours = getattr(profile, "avg_sleep_hours_per_day", None)
    exercise_minutes = getattr(profile, "avg_exercise_minutes_per_day", None)
    smoker = getattr(profile, "is_smoker", None)
    cig_packs = getattr(profile, "avg_cig_packs_per_week", None)
    alcohol = getattr(profile, "avg_alcohol_bottles_per_week", None)
    conditions = ops["split_text_items"](getattr(profile, "conditions", None))
    allergies = ops["split_text_items"](getattr(profile, "allergies", None))

    context.update(
        {
            "sleep_hours": sleep_hours,
            "exercise_minutes": exercise_minutes,
            "smoker": smoker,
            "cig_packs": cig_packs,
            "alcohol": alcohol,
            "conditions": conditions,
            "allergies": allergies,
        }
    )

    if ops["contains_any"](normalized, _PROFILE_SLEEP_KEYWORDS) and sleep_hours is not None:
        current_points.append(f"현재 기록상 수면은 하루 평균 {sleep_hours}시간입니다.")
    if ops["contains_any"](normalized, _PROFILE_EXERCISE_KEYWORDS) and exercise_minutes is not None:
        current_points.append(f"현재 기록상 운동은 하루 평균 {exercise_minutes}분입니다.")
    if ops["contains_any"](normalized, _PROFILE_SMOKING_KEYWORDS):
        if smoker is True and cig_packs is not None:
            current_points.append(f"현재 기록상 흡연 중이며 주간 흡연량은 {cig_packs}갑입니다.")
        elif smoker is True:
            current_points.append("현재 기록상 흡연 중으로 되어 있습니다.")
        elif smoker is False:
            current_points.append("현재 기록상 흡연하지 않는 것으로 되어 있습니다.")
    if ops["contains_any"](normalized, _PROFILE_ALCOHOL_KEYWORDS) and alcohol is not None:
        current_points.append(f"현재 기록상 주간 음주량은 {alcohol}병입니다.")
    return current_points, context


def _append_profile_fallback_current_points(*, current_points: list[str], context: dict[str, Any]) -> None:
    if current_points:
        return
    conditions = context.get("conditions") or []
    allergies = context.get("allergies") or []
    sleep_hours = context.get("sleep_hours")
    exercise_minutes = context.get("exercise_minutes")
    if conditions:
        current_points.append("현재 건강 상태로는 " + ", ".join(conditions[:2]) + "가 기록되어 있습니다.")
    if allergies:
        current_points.append("알레르기 정보는 " + ", ".join(allergies[:2]) + "입니다.")
    if sleep_hours is not None:
        current_points.append(f"수면은 하루 평균 {sleep_hours}시간으로 기록되어 있습니다.")
    if exercise_minutes is not None:
        current_points.append(f"운동은 하루 평균 {exercise_minutes}분으로 기록되어 있습니다.")


def _build_general_points_from_guide(*, normalized: str, guide: Any | None, ops: dict[str, Any]) -> list[str]:
    general_points: list[str] = []
    if not (guide and isinstance(guide.content_json, dict)):
        return general_points
    for section in guide.content_json.get("sections") or []:
        title = str(section.get("title") or "")
        body = str(section.get("body") or "").strip()
        if not body:
            continue

        match_topic = (
            (ops["contains_any"](normalized, _PROFILE_SLEEP_KEYWORDS) and ("수면" in title or "수면" in body))
            or (ops["contains_any"](normalized, _PROFILE_EXERCISE_KEYWORDS) and ("운동" in title or "활동" in body))
            or (ops["contains_any"](normalized, _PROFILE_SMOKING_KEYWORDS) and ("흡연" in title or "흡연" in body))
            or (ops["contains_any"](normalized, _PROFILE_ALCOHOL_KEYWORDS) and ("음주" in title or "음주" in body))
            or any(keyword in title for keyword in ["생활", "주의", "복약"])
        )
        if match_topic:
            line = ops["first_clean_line"](body)
            if line:
                general_points.append(line)
        if len(general_points) >= 3:
            break
    return general_points


def _build_next_points(
    *,
    normalized: str,
    profile: Any | None,
    adherence_summary: dict[str, Any] | None,
    context: dict[str, Any],
    ops: dict[str, Any],
) -> list[str]:
    next_points: list[str] = []
    sleep_hours = context.get("sleep_hours")
    exercise_minutes = context.get("exercise_minutes")

    if ops["contains_any"](normalized, _PROFILE_SLEEP_KEYWORDS) and sleep_hours is not None:
        if float(sleep_hours) < 6:
            next_points.append("수면 시간이 짧은 편이라 최근 증상 변화나 복용약 영향이 있는지도 함께 확인하는 것이 좋습니다.")
        elif float(sleep_hours) > 9:
            next_points.append("수면 시간이 긴 편이라 피로감이 계속되는지, 복용약 이후 졸림이 심해지지는 않는지 같이 보는 것이 좋습니다.")
    if ops["contains_any"](normalized, _PROFILE_EXERCISE_KEYWORDS) and exercise_minutes is not None and int(exercise_minutes) < 20:
        next_points.append("운동량이 적은 편이라 무리 없는 범위에서 가벼운 활동을 유지하는지 함께 보는 것이 좋습니다.")

    next_points.extend(ops["build_adherence_guidance_points"](adherence_summary=adherence_summary))
    if ops["contains_any"](normalized, ["잠", "수면", "못 자", "잠을 못", "잠이 안"]):
        next_points.append("최근 복용약 중 졸림이나 각성에 영향을 줄 수 있는 약이 있는지도 함께 보는 것이 좋습니다.")
        if profile and sleep_hours is not None:
            next_points.append("기록상 수면 시간이 충분해 보여도 실제로는 자주 깨는지, 자고 일어나도 피곤한지 같은 체감 변화를 함께 확인하는 것이 좋습니다.")
    if ops["contains_any"](normalized, ["술", "음주"]):
        next_points.append("음주와 현재 복용약의 조합은 따로 확인하는 것이 안전합니다.")
    if ops["contains_any"](normalized, ["담배", "흡연"]):
        next_points.append("흡연 여부는 호흡기 증상이나 일부 약 복용 시 주의점과 함께 보는 것이 좋습니다.")
    return next_points


def build_profile_guidance_sections(
    *,
    message: str,
    profile: Any | None,
    guide: Any | None,
    adherence_summary: dict[str, Any] | None,
    ops: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    normalized = (message or "").strip()
    current_points, context = _build_current_points(normalized=normalized, profile=profile, ops=ops)
    _append_profile_fallback_current_points(current_points=current_points, context=context)

    general_points = _build_general_points_from_guide(normalized=normalized, guide=guide, ops=ops)
    if not general_points:
        general_points.extend(build_profile_guidance_points(profile=profile, guide=guide, ops=ops)[:2])

    next_points = _build_next_points(
        normalized=normalized,
        profile=profile,
        adherence_summary=adherence_summary,
        context=context,
        ops=ops,
    )
    if not next_points:
        next_points.append("현재 기록에서 가장 먼저는 생활 습관 변화와 복약 흐름이 함께 흔들리고 있지 않은지부터 확인하는 것이 좋습니다.")

    return (
        ops["dedupe_lines"](current_points, limit=3),
        ops["dedupe_lines"](general_points, limit=3),
        ops["dedupe_lines"](next_points, limit=3),
    )
