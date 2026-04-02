from __future__ import annotations

from typing import Any


def answer_caregiver_check_intent(
    *,
    guide: Any | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    points: list[str] = []
    if guide and isinstance(guide.caregiver_summary, dict):
        for key in ("today_checklist", "care_points", "warning_signs"):
            value = guide.caregiver_summary.get(key) or []
            if isinstance(value, list):
                points.extend(str(item).strip() for item in value if str(item).strip())
    if not points and schedules:
        schedule_text = ops["build_schedule_text"](schedules, meds)
        points.append(f"오늘 복약 일정 확인: {schedule_text}")

    if not points:
        base = f"{target_label} 기준으로 오늘 보호자가 확인할 체크포인트 정보가 아직 충분하지 않습니다."
    else:
        deduped: list[str] = []
        for point in points:
            if point not in deduped:
                deduped.append(point)
        base = f"{target_label} 기준으로 오늘 보호자가 확인해야 할 내용은 다음과 같습니다.\n" + "\n".join(
            f"- {point}" for point in deduped[:5]
        )

    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def answer_self_check_intent(
    *,
    guide: Any | None,
    meds: list[dict[str, Any]],
    schedules: list[dict[str, Any]],
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    points: list[str] = []
    if schedules:
        schedule_text = ops["build_schedule_text"](schedules, meds)
        for line in schedule_text.splitlines():
            clean = line.strip().lstrip("-").strip()
            if clean:
                points.append(clean)
    if guide and isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            title = str(section.get("title") or "")
            body = str(section.get("body") or "").strip()
            if "주의" in title or "생활" in title:
                for line in body.splitlines():
                    clean = line.strip().lstrip("-").strip()
                    if clean:
                        points.append(clean)

    deduped: list[str] = []
    for point in points:
        if point not in deduped:
            deduped.append(point)
    if deduped:
        base = f"{target_label} 기준으로 오늘 본인이 확인하면 좋은 체크리스트는 다음과 같습니다.\n" + "\n".join(
            f"- {point}" for point in deduped[:4]
        )
    else:
        base = f"{target_label} 기준으로 오늘 확인할 체크리스트 정보가 아직 충분하지 않습니다."
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base


def answer_allergy_food_intent(
    *,
    profile: Any | None,
    target_label: str,
    requester_role: Any,
    audience: str,
    ops: dict[str, Any],
) -> str:
    allergies = ops["split_text_items"](getattr(profile, "allergies", None) if profile else None)
    if allergies:
        base = f"{target_label} 기준으로 특히 조심해야 할 알레르기/음식 정보는 다음과 같습니다.\n" + "\n".join(
            f"- {item}" for item in allergies
        )
    else:
        base = f"{target_label} 기준으로 등록된 알레르기나 음식 주의 정보는 아직 없습니다."
    return ops["to_caregiver_style"](answer=base, audience=audience) if requester_role == ops["caregiver_role"] else base
