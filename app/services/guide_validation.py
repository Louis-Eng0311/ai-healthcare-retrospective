from __future__ import annotations

import re
from typing import Any

DEFAULT_GUIDE_DISCLAIMER = "본 가이드는 의료 자문이 아닌 참고용 건강 정보입니다."

_REQUIRED_SECTION_TITLES = {
    "복약 핵심",
    "생활 관리",
    "주의 신호",
}

_BANNED_PATTERNS = [
    r"완치됩니다",
    r"절대 안전",
    r"무조건 괜찮",
    r"반드시 완치",
    r"의사 상담 없이",
]

_REQUIRED_CAREGIVER_KEYS = {
    "today_checklist",
    "warning_signs",
    "care_points",
}


# 기본 면책 문구 반환
def get_guide_disclaimer() -> str:
    return DEFAULT_GUIDE_DISCLAIMER


# 문자열 필드 검증
def _require_non_empty_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required")

    return normalized


# 리스트[str] 필드 검증
def _require_string_list(value: Any, *, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")

    normalized_items: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            raise ValueError(f"{field_name}[{idx}] must be a string")

        text = item.strip()
        if not text:
            raise ValueError(f"{field_name}[{idx}] is empty")

        normalized_items.append(text)

    return normalized_items


# 과도한 단정 표현 검사
def _assert_no_overconfident_medical_claims(content_text: str) -> None:
    for pattern in _BANNED_PATTERNS:
        if re.search(pattern, content_text, flags=re.IGNORECASE):
            raise ValueError("content_text contains overconfident medical statement")


# content_json 구조 검증
def _validate_content_json(content_json: Any) -> dict[str, Any]:
    if not isinstance(content_json, dict):
        raise ValueError("content_json must be a dict")

    sections = content_json.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("content_json.sections is required")

    seen_titles: set[str] = set()
    normalized_sections: list[dict[str, str]] = []

    for idx, section in enumerate(sections):
        if not isinstance(section, dict):
            raise ValueError(f"content_json.sections[{idx}] must be a dict")

        title = _require_non_empty_string(
            section.get("title"),
            field_name=f"content_json.sections[{idx}].title",
        )
        body = _require_non_empty_string(
            section.get("body"),
            field_name=f"content_json.sections[{idx}].body",
        )

        seen_titles.add(title)
        normalized_sections.append(
            {
                "title": title,
                "body": body,
            }
        )

    missing_titles = _REQUIRED_SECTION_TITLES - seen_titles
    if missing_titles:
        raise ValueError(f"content_json.sections missing required titles: {sorted(missing_titles)}")

    return {
        "sections": normalized_sections,
    }


# caregiver_summary 구조 검증
def _validate_caregiver_summary(caregiver_summary: Any) -> dict[str, Any]:
    if not isinstance(caregiver_summary, dict):
        raise ValueError("caregiver_summary must be a dict")

    missing_keys = _REQUIRED_CAREGIVER_KEYS - set(caregiver_summary.keys())
    if missing_keys:
        raise ValueError(f"caregiver_summary missing required keys: {sorted(missing_keys)}")

    return {
        "today_checklist": _require_string_list(
            caregiver_summary.get("today_checklist"),
            field_name="caregiver_summary.today_checklist",
        ),
        "warning_signs": _require_string_list(
            caregiver_summary.get("warning_signs"),
            field_name="caregiver_summary.warning_signs",
        ),
        "care_points": _require_string_list(
            caregiver_summary.get("care_points"),
            field_name="caregiver_summary.care_points",
        ),
    }


# guide payload 전체 검증
def validate_guide_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("guide payload must be a dict")

    content_text = _require_non_empty_string(
        payload.get("content_text"),
        field_name="content_text",
    )
    _assert_no_overconfident_medical_claims(content_text)

    content_json = _validate_content_json(payload.get("content_json"))
    caregiver_summary = _validate_caregiver_summary(payload.get("caregiver_summary"))

    disclaimer = payload.get("disclaimer")
    if disclaimer is None:
        disclaimer = get_guide_disclaimer()
    disclaimer = _require_non_empty_string(disclaimer, field_name="disclaimer")

    return {
        "content_text": content_text,
        "content_json": content_json,
        "caregiver_summary": caregiver_summary,
        "disclaimer": disclaimer,
    }
