from __future__ import annotations

import re
from typing import Any


def normalize_user_message(content: str) -> str:
    normalized = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def log_chat_metric(*, event: str, logger: Any, **fields: Any) -> None:
    payload = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.info("chat_metric event=%s %s", event, payload)


def apply_response_contract(
    *,
    content: str,
    is_emergency: bool,
    emergency_message: str | None,
    disclaimer: str,
) -> str:
    normalized = normalize_user_message(content)
    if not normalized:
        normalized = "질문을 정확히 이해하지 못했어요. 확인하고 싶은 내용을 한 줄로 다시 알려주세요."

    if is_emergency:
        emergency_line = emergency_message or "응급 상황이 의심됩니다. 즉시 119 또는 가까운 응급실에 연락해 주세요."
        if "119" not in normalized and "응급실" not in normalized:
            normalized = f"{normalized}\n\n{emergency_line}"

    if disclaimer not in normalized:
        normalized = f"{normalized}\n\n{disclaimer}"

    return normalized

