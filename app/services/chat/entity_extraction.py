from __future__ import annotations

import re
from typing import Any

from app.services.chat.keywords import (
    _EXTERNAL_DRUG_CONTEXT_KEYWORDS,
    _EXTERNAL_DRUG_QUERY_KEYWORDS,
    _EXTERNAL_DRUG_STOPWORDS,
    _EXTERNAL_DRUG_SUFFIXES,
    _EXTERNAL_MED_FOLLOWUP_KEYWORDS,
    _FOLLOWUP_MED_REFERENCES,
    _MED_LIST_KEYWORDS,
)
from app.services.chat.quality import normalize_user_message
from app.services.chat.text_utils import (
    contains_any,
    contains_keyword,
    extract_bracketed_drug_name,
    find_best_med_match,
)

_EXTERNAL_NAME_PATTERNS = [
    re.compile(r"([가-힣A-Za-z0-9]+)라고\s*알아"),
    re.compile(r"([가-힣A-Za-z0-9]+)라는\s*약"),
    re.compile(r"([가-힣A-Za-z0-9]+)은\s*어떤\s*약"),
    re.compile(r"([가-힣A-Za-z0-9]+)[이가은는]\s*무슨\s*약"),
    re.compile(r"([가-힣A-Za-z0-9]+)[이가은는]\s*어떤\s*약"),
    re.compile(r"([가-힣A-Za-z0-9]+)[이가은는]\s*뭐야"),
    re.compile(r"([가-힣A-Za-z0-9]+)에\s*대해서\s*알려"),
    re.compile(r"([가-힣A-Za-z0-9]+)에대해서\s*알려"),
    re.compile(r"([가-힣A-Za-z0-9]+)\s*알려줘"),
    re.compile(r"([가-힣A-Za-z0-9]+)\s*설명해줘"),
    re.compile(r"([가-힣A-Za-z0-9]+)의\s*(용도|주의사항|부작용)"),
    re.compile(r"([가-힣A-Za-z0-9]+)[를을은는이가]\s*(새로\s*처방|처방받|먹는\s*약|용도|부작용|주의사항)"),
    re.compile(r"([가-힣A-Za-z0-9]+)\s*정보좀"),
    re.compile(r"([가-힣A-Za-z0-9]+)\s*정보\s*좀"),
]


def _extract_named_candidate(text: str) -> str | None:
    for pattern in _EXTERNAL_NAME_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        candidate = match.group(1).strip()
        if len(candidate) >= 2 and candidate not in _EXTERNAL_DRUG_STOPWORDS:
            return candidate
    return None


def _extract_context_candidate(text: str) -> str | None:
    if not contains_any(text, _EXTERNAL_DRUG_CONTEXT_KEYWORDS + _EXTERNAL_DRUG_QUERY_KEYWORDS):
        return None
    tokens = [token.strip() for token in re.split(r"[\s,./()]+", text) if token.strip()]
    preferred: list[str] = []
    for token in tokens:
        if token in _EXTERNAL_DRUG_STOPWORDS or len(token) < 2:
            continue
        if contains_any(token, _EXTERNAL_DRUG_CONTEXT_KEYWORDS):
            continue
        if any(ch.isdigit() for ch in token):
            continue
        if any(token.endswith(suffix) for suffix in _EXTERNAL_DRUG_SUFFIXES):
            preferred.append(token)
    return preferred[0] if preferred else None


def extract_external_drug_name(
    message: str,
    recent_messages: list[Any] | None = None,
    *,
    session_memory: Any | None = None,
) -> str | None:
    normalized = normalize_user_message(message)
    bracketed_name = extract_bracketed_drug_name(normalized)
    if bracketed_name:
        return bracketed_name
    if contains_any(
        normalized,
        _MED_LIST_KEYWORDS
        + ["현재 약", "지금 먹는 약", "복용약", "현재 복용약", "같이 먹", "함께 먹", "조합", "상호작용"],
    ):
        return None

    direct = _extract_named_candidate(normalized)
    if direct:
        return direct

    contextual = _extract_context_candidate(normalized)
    if contextual:
        return contextual

    if recent_messages and contains_any(normalized, _EXTERNAL_MED_FOLLOWUP_KEYWORDS):
        for recent in reversed(recent_messages):
            recent_content = str(getattr(recent, "content", "") or "").strip()
            if not recent_content:
                continue
            direct_recent = _extract_named_candidate(recent_content)
            if direct_recent:
                return direct_recent
            contextual_recent = _extract_context_candidate(recent_content)
            if contextual_recent:
                return contextual_recent

    if session_memory and contains_any(normalized, _FOLLOWUP_MED_REFERENCES + _EXTERNAL_MED_FOLLOWUP_KEYWORDS):
        remembered_name = str(getattr(session_memory, "recent_external_drug_name", "") or "").strip()
        if remembered_name:
            return remembered_name
    return None


def extract_target_med(
    *,
    message: str,
    meds: list[dict[str, Any]],
    recent_messages: list[Any] | None = None,
    session_memory: Any | None = None,
) -> dict[str, Any] | None:
    normalized = normalize_user_message(message)
    bracketed_name = extract_bracketed_drug_name(normalized)
    if bracketed_name:
        for med in meds:
            name = str(med.get("display_name") or "").strip()
            if name and (contains_keyword(bracketed_name, name) or contains_keyword(name, bracketed_name)):
                return med

    for med in meds:
        name = str(med.get("display_name") or "").strip()
        if name and contains_keyword(normalized, name):
            return med

    fuzzy_matched = find_best_med_match(query=normalized, meds=meds)
    if fuzzy_matched:
        return fuzzy_matched

    if recent_messages and contains_any(normalized, _FOLLOWUP_MED_REFERENCES):
        for recent in reversed(recent_messages):
            recent_content = str(getattr(recent, "content", "") or "")
            for med in meds:
                name = str(med.get("display_name") or "").strip()
                if name and contains_keyword(recent_content, name):
                    return med

    if session_memory and contains_any(normalized, _FOLLOWUP_MED_REFERENCES):
        remembered_name = str(getattr(session_memory, "recent_drug_name", "") or "").strip()
        if remembered_name:
            for med in meds:
                name = str(med.get("display_name") or "").strip()
                if name and name == remembered_name:
                    return med

    return None
