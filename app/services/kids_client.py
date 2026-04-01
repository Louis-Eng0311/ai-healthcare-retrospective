from __future__ import annotations

import html
import os
import re
from typing import Any

import httpx

# KIDS 키가 없으면 MFDS 키를 fallback 으로 사용
_KIDS_API_KEY = (os.getenv("KIDS_API_KEY", "") or os.getenv("MFDS_SERVICE_KEY", "") or "").strip()

# KIDS 자동변환 OpenAPI 실제 호출 URL (최신 버전 기준)
_KIDS_COMBO_TABOO_URL = "https://api.odcloud.kr/api/15089525/v1/uddi:3f2efdac-942b-494e-919f-8bdc583f65ea"  # 병용금기
_KIDS_PREGNANT_TABOO_URL = (
    "https://api.odcloud.kr/api/15089735/v1/uddi:19f45c87-cd76-4a8a-92e6-d394cc688a47"  # 임부금기
)
_KIDS_AGE_TABOO_URL = "https://api.odcloud.kr/api/15089531/v1/uddi:54d76703-95c8-4ac3-9a69-f54cb1d93fb0"  # 연령금기
_KIDS_OLDMAN_CARE_URL = "https://api.odcloud.kr/api/15089521/v1/uddi:a6bb0e38-51cc-4dbe-8d01-c049adebd938"  # 노인주의
_KIDS_EFFICACY_GROUP_OVERLAP_URL = (
    "https://api.odcloud.kr/api/15089542/v1/uddi:54330912-f350-4bfc-a7ca-e90f13f8cc50"  # 효능군중복주의
)
_KIDS_TIMEOUT_SECONDS = float((os.getenv("KIDS_TIMEOUT_SECONDS", "4.0") or "4.0").strip())


def _clean_text(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    s = html.unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&nbsp;", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_drug_name(drug_name: str) -> str:
    name = (drug_name or "").strip()
    name = html.unescape(name)
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"\[.*?\]", " ", name)
    name = re.sub(r"\d+(\.\d+)?\s*(mg|ml|g|mcg|㎎|㎖|그램)", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\d+", " ", name)
    name = re.sub(
        r"(tablet|tab|cap|capsule|softcap|soft capsule|정|캡슐|연질캡슐|필름코팅정|서방정|산|시럽|주사액|주사제)",
        " ",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"[/,+\-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    # odcloud 자동변환 API는 보통 data 키 사용
    if isinstance(payload.get("data"), list):
        return [x for x in payload["data"] if isinstance(x, dict)]

    cur = payload

    if "response" in cur and isinstance(cur["response"], dict):
        cur = cur["response"]

    if "body" in cur and isinstance(cur["body"], dict):
        cur = cur["body"]

    items = cur.get("items")
    if items is None:
        items = cur.get("data")

    if items is None:
        return []

    if isinstance(items, dict) and "item" in items:
        items = items["item"]

    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    if isinstance(items, dict):
        return [items]

    return []


def _safe_get(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in obj and obj[key] is not None:
            value = _clean_text(obj[key])
            if value:
                return value
    return ""


class KIDSClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = (api_key or _KIDS_API_KEY or "").strip()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    async def _get_json(
        self, url: str, params: dict[str, Any], timeout: float = _KIDS_TIMEOUT_SECONDS
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def _search_dataset(self, *, url: str, drug_name: str) -> list[dict[str, Any]]:
        keyword = _normalize_drug_name(drug_name)
        raw_keyword = _clean_text(drug_name)

        if not keyword and not raw_keyword:
            return []

        # odcloud 자동변환 API는 page/perPage/serviceKey 조합이 기본
        # 검색 파라미터명은 데이터셋마다 달라서 후보를 순차 시도
        search_keywords = []
        if keyword:
            search_keywords.append(keyword)
        if raw_keyword and raw_keyword not in search_keywords:
            search_keywords.append(raw_keyword)

        param_candidates: list[dict[str, Any]] = []
        for kw in search_keywords:
            param_candidates.extend(
                [
                    {"serviceKey": self.api_key, "page": 1, "perPage": 30, "itemName": kw},
                    {"serviceKey": self.api_key, "page": 1, "perPage": 30, "drugName": kw},
                    {"serviceKey": self.api_key, "page": 1, "perPage": 30, "ingrName": kw},
                    {"serviceKey": self.api_key, "page": 1, "perPage": 30, "name": kw},
                    {"serviceKey": self.api_key, "page": 1, "perPage": 30, "keyword": kw},
                ]
            )

        # 검색 파라미터 없이도 한 번 시도
        param_candidates.append({"serviceKey": self.api_key, "page": 1, "perPage": 30})

        for params in param_candidates:
            try:
                payload = await self._get_json(url, params)
                items = _extract_items(payload)
                if items:
                    return items
            except httpx.HTTPError:
                continue
            except Exception:
                continue

        return []

    def _map_items(self, *, items: list[dict[str, Any]], source: str, title: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for item in items:
            drug_name = _safe_get(
                item,
                "itemName",
                "ITEM_NAME",
                "품목명",
                "제품명",
                "productName",
                "drugName",
                "의약품명",
            )
            ingredient = _safe_get(
                item,
                "ingrName",
                "INGR_NAME",
                "성분명",
                "주성분",
                "ingredientName",
            )
            summary = _safe_get(
                item,
                "PROHBT_CONTENT",
                "prohbtContent",
                "금기내용",
                "주의내용",
                "CONTENT",
                "content",
                "상세내용",
                "detail",
                "DUR_CONTENT",
                "durContent",
                "description",
                "설명",
            )

            if not summary:
                pairs = []
                for k, v in item.items():
                    text = _clean_text(v)
                    if text:
                        pairs.append(f"{k}={text}")
                summary = " / ".join(pairs[:8])

            content_parts = []
            if drug_name:
                content_parts.append(f"품목명: {drug_name}")
            if ingredient:
                content_parts.append(f"성분명: {ingredient}")
            if summary:
                content_parts.append(summary)

            content = " / ".join([x for x in content_parts if x])
            if not content:
                continue

            results.append(
                {
                    "source": source,
                    "title": title,
                    "content": content,
                }
            )

        return results

    async def search_safety_evidence(self, drug_name: str) -> list[dict[str, Any]]:
        if not self.is_enabled():
            return []

        all_results: list[dict[str, Any]] = []

        datasets = [
            (_KIDS_COMBO_TABOO_URL, "kids_combo_taboo", "KIDS 병용금기"),
            (_KIDS_PREGNANT_TABOO_URL, "kids_pregnant_taboo", "KIDS 임부주의"),
            (_KIDS_AGE_TABOO_URL, "kids_age_taboo", "KIDS 연령금기"),
            (_KIDS_OLDMAN_CARE_URL, "kids_oldman_care", "KIDS 노인주의"),
            (_KIDS_EFFICACY_GROUP_OVERLAP_URL, "kids_efficacy_group_overlap", "KIDS 효능군중복주의"),
        ]

        for url, source, title in datasets:
            try:
                items = await self._search_dataset(url=url, drug_name=drug_name)
                mapped = self._map_items(items=items, source=source, title=title)
                all_results.extend(mapped)
            except httpx.HTTPError:
                continue
            except Exception:
                continue

        # 중복 제거
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for item in all_results:
            key = (
                _clean_text(item.get("source")),
                _clean_text(item.get("title")),
                _clean_text(item.get("content")),
            )
            if not key[2]:
                continue
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped[:20]
