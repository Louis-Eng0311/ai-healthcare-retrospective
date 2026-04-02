from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from app.services.chat.keywords import _MED_QUERY_STOPWORDS
from app.services.chat.quality import normalize_user_message

_MED_QUERY_STOPWORD_SET = {str(item).lower() for item in _MED_QUERY_STOPWORDS}


def mask_log_value(value: str, *, keep: int = 12) -> str:
    clean = normalize_user_message(value)
    if len(clean) <= keep:
        return clean
    return clean[:keep] + "..."


def extract_bracketed_drug_name(message: str) -> str | None:
    normalized = normalize_user_message(message)
    match = re.fullmatch(r"[\(\[\{＜<]\s*([가-힣A-Za-z0-9+\-_/\.]{2,60})\s*[\)\]\}＞>]", normalized)
    if not match:
        return None
    candidate = str(match.group(1) or "").strip()
    if len(candidate) < 2:
        return None
    return candidate


@lru_cache(maxsize=8192)
def _compact_text_cached(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isalnum() or ("가" <= ch <= "힣"))


def compact_text(value: str) -> str:
    return _compact_text_cached(str(value or ""))


@lru_cache(maxsize=16384)
def _contains_keyword_cached(message: str, keyword: str) -> bool:
    if keyword in message:
        return True
    return compact_text(keyword) in compact_text(message)


def contains_keyword(message: str, keyword: str) -> bool:
    return _contains_keyword_cached(str(message or "").strip(), str(keyword or ""))


@lru_cache(maxsize=4096)
def _contains_any_cached(message: str, keywords: tuple[str, ...]) -> bool:
    return any(contains_keyword(message, keyword) for keyword in keywords)


def contains_any(message: str, keywords: list[str] | tuple[str, ...]) -> bool:
    return _contains_any_cached(str(message or "").strip(), tuple(str(keyword or "") for keyword in keywords))


def strip_korean_postposition(token: str) -> str:
    clean = str(token or "").strip()
    for suffix in (
        "이에요",
        "예요",
        "이야",
        "야",
        "이니",
        "니",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "에",
        "도",
        "만",
    ):
        if clean.endswith(suffix) and len(clean) > len(suffix) + 1:
            return clean[: -len(suffix)]
    return clean


def dedupe_lines(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        results.append(clean)
        if limit is not None and len(results) >= limit:
            break
    return results


def extract_med_query_tokens(message: str) -> list[str]:
    normalized = str(message or "").strip()
    if not normalized:
        return []

    candidates = [normalized]
    for token in re.split(r"[\s,./()]+", normalized):
        stripped = strip_korean_postposition(token)
        compact = compact_text(stripped)
        if len(compact) < 2:
            continue
        if compact.lower() in _MED_QUERY_STOPWORD_SET:
            continue
        candidates.append(stripped)

    return dedupe_lines(candidates, limit=8)


def find_best_med_match(
    *,
    query: str,
    meds: list[dict[str, Any]],
    threshold: float = 0.72,
) -> dict[str, Any] | None:
    tokens = extract_med_query_tokens(query)
    if not tokens or not meds:
        return None

    exact_candidates = [compact_text(token).lower() for token in tokens]
    for med in meds:
        med_name = str(med.get("display_name") or "").strip()
        compact_name = compact_text(med_name).lower()
        if not compact_name:
            continue
        if any(compact_name in token or token in compact_name for token in exact_candidates if len(token) >= 2):
            return med

    best_med: dict[str, Any] | None = None
    best_score = 0.0
    for med in meds:
        med_name = str(med.get("display_name") or "").strip()
        compact_name = compact_text(med_name).lower()
        if len(compact_name) < 2:
            continue
        for token in exact_candidates:
            if len(token) < 2:
                continue
            score = SequenceMatcher(None, token, compact_name).ratio()
            if score > best_score:
                best_score = score
                best_med = med

    return best_med if best_score >= threshold else None


def split_text_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    raw = str(value or "").strip()
    if not raw:
        return []

    if raw.startswith("[") and raw.endswith("]"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

    return [
        item.strip().strip('"').strip("'") for chunk in raw.splitlines() for item in chunk.split(",") if item.strip()
    ]


def append_unique(items: list[str], value: str | None) -> None:
    clean = str(value or "").strip()
    if clean and clean not in items:
        items.append(clean)


def first_clean_line(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for line in raw.splitlines():
        clean = line.strip().lstrip("-").strip()
        if clean:
            return clean
    return raw


def summarize_text(value: str | None, *, max_sentences: int = 2) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    compact = re.sub(r"(?<=[.!?])(?=[가-힣A-Za-z0-9])", " ", raw)
    compact = compact.replace("이 약을 복용하기 전에", ". 이 약을 복용하기 전에")
    compact = compact.replace("정해진 용법과 용량을 잘 지키십시오.", "정해진 용법과 용량을 잘 지키십시오. ")
    compact = re.sub(r"\s+", " ", compact)
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+|(?<=다\.)\s*", compact) if item.strip()]
    if not sentences:
        return compact
    return " ".join(sentences[:max_sentences]).strip()


def choose_korean_particle(word: str, pair: tuple[str, str]) -> str:
    text = str(word or "").strip()
    if not text:
        return pair[1]
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        return pair[0] if has_batchim else pair[1]
    return pair[1]


def with_particle(word: str, pair: tuple[str, str]) -> str:
    text = str(word or "").strip()
    return text + choose_korean_particle(text, pair)
