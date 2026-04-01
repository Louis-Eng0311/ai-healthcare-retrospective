from __future__ import annotations

import json
from typing import Any

from app.models.guides import Guide
from app.models.patients import PatientProfile


def append_rag_block(blocks: list[dict[str, Any]], *, source: str, title: str, content: str) -> None:
    text = (content or "").strip()
    if not text:
        return
    blocks.append(
        {
            "source": source,
            "title": title,
            "content": text,
        }
    )


def extract_guide_blocks(guide: Guide | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not guide:
        return blocks

    if guide.content_text:
        append_rag_block(
            blocks,
            source="guide_text",
            title="최신 가이드 본문",
            content=guide.content_text,
        )

    if isinstance(guide.content_json, dict):
        for section in guide.content_json.get("sections") or []:
            append_rag_block(
                blocks,
                source="guide_section",
                title=str(section.get("title") or "가이드 섹션"),
                content=str(section.get("body") or ""),
            )

    if isinstance(guide.caregiver_summary, dict):
        append_rag_block(
            blocks,
            source="guide_caregiver_summary",
            title="보호자 요약",
            content=json.dumps(guide.caregiver_summary, ensure_ascii=False),
        )

    return blocks


def extract_profile_blocks(profile: PatientProfile | None) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if not profile:
        return blocks

    profile_map = {
        "흡연 정보": getattr(profile, "avg_cig_packs_per_week", None),
        "음주 정보": getattr(profile, "avg_alcohol_bottles_per_week", None),
        "수면 정보": getattr(profile, "avg_sleep_hours_per_day", None),
        "운동 정보": getattr(profile, "avg_exercise_minutes_per_day", None),
        "기저질환": getattr(profile, "conditions", None),
        "알레르기": getattr(profile, "allergies", None),
        "메모": getattr(profile, "notes", None),
    }

    for title, value in profile_map.items():
        if value is not None and str(value).strip():
            append_rag_block(
                blocks,
                source="profile",
                title=title,
                content=str(value),
            )

    return blocks


def extract_schedule_blocks(schedule_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if schedule_text and schedule_text != "등록된 복약 일정 없음":
        append_rag_block(
            blocks,
            source="schedule",
            title="복약 일정",
            content=schedule_text,
        )
    return blocks


def extract_meds_blocks(meds_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if meds_text and meds_text != "현재 복용 약 정보 없음":
        append_rag_block(
            blocks,
            source="meds",
            title="현재 복용 약",
            content=meds_text,
        )
    return blocks


def extract_external_blocks(
    *,
    mfds_evidence: list[dict[str, Any]],
    kids_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    for item in mfds_evidence:
        append_rag_block(
            blocks,
            source="mfds",
            title=str(item.get("title") or "MFDS 근거"),
            content=str(item.get("content") or ""),
        )

    for item in kids_evidence:
        append_rag_block(
            blocks,
            source="kids",
            title=str(item.get("title") or "KIDS 근거"),
            content=str(item.get("content") or ""),
        )

    return blocks


def build_rag_context(
    *,
    intent: str,
    guide_blocks: list[dict[str, Any]],
    profile_blocks: list[dict[str, Any]],
    schedule_blocks: list[dict[str, Any]],
    meds_blocks: list[dict[str, Any]],
    external_blocks: list[dict[str, Any]],
    limit: int = 8,
) -> list[dict[str, Any]]:
    if intent in {"profile_smoking", "profile_alcohol", "profile_sleep", "profile_exercise"}:
        ordered = profile_blocks + guide_blocks + schedule_blocks + meds_blocks + external_blocks
    elif intent == "schedule":
        ordered = schedule_blocks + meds_blocks + guide_blocks + profile_blocks + external_blocks
    elif intent == "medication_caution":
        ordered = guide_blocks + external_blocks + meds_blocks + schedule_blocks + profile_blocks
    elif intent == "guide":
        ordered = guide_blocks + meds_blocks + schedule_blocks + profile_blocks + external_blocks
    else:
        ordered = guide_blocks + meds_blocks + schedule_blocks + profile_blocks + external_blocks

    return ordered[:limit]
