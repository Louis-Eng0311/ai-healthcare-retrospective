from __future__ import annotations

from typing import Any


def build_fact_summary(
    *,
    analysis: Any,
    context: Any,
    target_label: str,
    ops: dict[str, Any],
) -> str:
    points: list[str] = []

    if analysis.target_med:
        med_name = str(analysis.target_med.get("display_name") or "").strip()
        dosage = str(analysis.target_med.get("dosage") or "").strip()
        notes = str(analysis.target_med.get("notes") or "").strip()
        source_document_id = analysis.target_med.get("source_document_id")
        if med_name:
            line = med_name
            if dosage:
                line += f" {dosage}"
            if notes:
                line += f" / {notes}"
            points.append("현재 기록 약 정보: " + line)
        if source_document_id:
            points.append(f"확정 약 출처 문서: #{source_document_id}")
        patient_med_id = analysis.target_med.get("patient_med_id")
        schedule_lines: list[str] = []
        for schedule in context.schedules:
            if schedule.get("patient_med_id") != patient_med_id:
                continue
            for item in schedule.get("times") or []:
                schedule_lines.append(
                    f"{ops['humanize_days'](item.get('days_of_week'))} {ops['humanize_time'](item.get('time_of_day'))}".strip()
                )
        if schedule_lines:
            points.append("복용 시간: " + ", ".join(schedule_lines[:3]))
        points.extend(ops["extract_dur_alert_points"](dur_alerts=context.dur_alerts, med_name=med_name, limit=2))
        points.extend(ops["build_med_adherence_points"](med_name=med_name, adherence_summary=context.adherence_summary))

    if analysis.external_drug_name:
        points.append(f"질문 약 이름: {analysis.external_drug_name}")
        if not any(
            ops["contains_keyword"](str(med.get("display_name") or ""), analysis.external_drug_name) for med in context.meds
        ):
            points.append("현재 복용약 목록에는 없음")

    if analysis.target_condition:
        points.append(f"질문 질환: {analysis.target_condition}")

    if analysis.primary_intent in {"profile_body", "profile_summary"} and context.profile:
        if getattr(context.profile, "height_cm", None) is not None:
            points.append(f"키: {context.profile.height_cm}cm")
        if getattr(context.profile, "weight_kg", None) is not None:
            points.append(f"몸무게: {context.profile.weight_kg}kg")
        if getattr(context.profile, "bmi", None) is not None:
            points.append(f"BMI: {context.profile.bmi}")

    if analysis.primary_intent == "hospital_schedule" and context.hospital_schedules:
        next_schedule = context.hospital_schedules[0]
        title = str(getattr(next_schedule, "title", "") or "병원 일정").strip()
        scheduled_at = ops["format_datetime_korean"](getattr(next_schedule, "scheduled_at", None))
        hospital_name = str(getattr(next_schedule, "hospital_name", "") or "").strip()
        line = f"다음 병원 일정: {scheduled_at} / {title}"
        if hospital_name:
            line += f" / {hospital_name}"
        points.append(line)

    conditions = ops["split_text_items"](getattr(context.profile, "conditions", None) if context.profile else None)
    allergies = ops["split_text_items"](getattr(context.profile, "allergies", None) if context.profile else None)
    if conditions:
        points.append("건강 상태: " + ", ".join(conditions[:3]))
    if allergies:
        points.append("알레르기: " + ", ".join(allergies[:3]))

    if analysis.primary_intent in {"med_list", "schedule", "med_time_split"} and context.meds:
        med_names = [
            str(med.get("display_name") or "").strip()
            for med in context.meds
            if str(med.get("display_name") or "").strip()
        ]
        if med_names:
            points.append(f"{target_label} 현재 복용약: " + ", ".join(med_names[:4]))

    if (
        analysis.primary_intent == "general_caution"
        and context.latest_guide
        and isinstance(context.latest_guide.content_json, dict)
    ):
        for section in context.latest_guide.content_json.get("sections") or []:
            title = str(section.get("title") or "").strip()
            body = str(section.get("body") or "").strip()
            if ("주의" in title or "생활" in title or "신호" in title) and body:
                points.append(f"{title}: {ops['first_clean_line'](body)}")
            if len(points) >= 5:
                break

    if analysis.primary_intent in {"general_caution", "profile_guidance", "adherence_priority", "tonight_check"}:
        points.extend(ops["build_adherence_guidance_points"](adherence_summary=context.adherence_summary))

    deduped = ops["dedupe_lines"](points, limit=6)
    return "\n".join(f"- {item}" for item in deduped) if deduped else "질문 관련 결정적 사실이 아직 충분하지 않습니다."
