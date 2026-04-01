import re
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException
from starlette import status

from app.core import config
from app.dtos.documents import MfdsDrugItemResponse, MfdsDrugSearchResponse
from app.models.medications import DrugInfoCache


class MfdsService:
    _NEDRUG_SEARCH_URL = "https://nedrug.mfds.go.kr/searchDrug"
    _NEDRUG_ITEM_SEQ_PATTERN = re.compile(r'href="/pbp/CCBBB01/getItemDetail\?itemSeq=(\d+)"', re.IGNORECASE)

    # 식약처 약 정보 검색 - REQ-DRUG-001, REQ-DRUG-002
    async def search_easy_drug_info(self, drug_name: str, num_of_rows: int = 5) -> MfdsDrugSearchResponse:
        if not config.MFDS_SERVICE_KEY:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVICE_UNAVAILABLE")

        normalized_query = str(drug_name or "").strip()
        search_candidates = self._build_easy_drug_search_candidates(drug_name=normalized_query)
        if self._looks_like_standard_code(normalized_query):
            standard_code = self._extract_digits(value=normalized_query)
            resolved_item_seqs = await self._resolve_item_seq_candidates_by_standard_code(standard_code=standard_code)
            search_candidates = self._prepend_item_seq_candidates(
                candidates=search_candidates,
                item_seqs=resolved_item_seqs,
            )

        items: list[dict] = []
        for query_field, query_value in search_candidates:
            items = await self._request_easy_drug_info(
                query=query_value,
                num_of_rows=num_of_rows,
                query_field=query_field,
            )
            if items:
                break

        # e약은요 미매칭 시 DUR 품목정보 fallback 조회
        if not items:
            for query_field, query_value in search_candidates:
                items = await self._request_dur_item_info(
                    query=query_value,
                    num_of_rows=num_of_rows,
                    query_field=query_field,
                )
                if items:
                    break

        await self._sync_drug_info_cache(items=items)

        response_items = [
            MfdsDrugItemResponse(
                item_seq=str(self._pick(item, "ITEM_SEQ", "itemSeq") or ""),
                item_name=str(self._pick(item, "ITEM_NAME", "itemName") or ""),
                entp_name=self._nullable_str(self._pick(item, "ENTP_NAME", "entpName")),
                item_image=self._nullable_str(self._pick(item, "ITEM_IMAGE", "itemImage", "BIG_PRDT_IMG_URL")),
                efficacy=self._nullable_str(self._pick(item, "EE_DOC_DATA", "efcyQesitm")),
                dosage_info=self._nullable_str(self._pick(item, "UD_DOC_DATA", "useMethodQesitm")),
                precautions=self._nullable_str(self._pick(item, "NB_DOC_DATA", "atpnQesitm", "atpnWarnQesitm")),
            )
            for item in items
        ]

        return MfdsDrugSearchResponse(
            query=normalized_query or drug_name, total=len(response_items), items=response_items
        )

    # 식약처 e약은요 API 호출 - REQ-DRUG-001, REQ-DRUG-002
    async def _request_easy_drug_info(self, query: str, num_of_rows: int, query_field: str = "itemName") -> list[dict]:
        url = f"{config.MFDS_BASE_URL}/DrbEasyDrugInfoService/getDrbEasyDrugList"
        if query_field not in {"itemName", "itemSeq"}:
            query_field = "itemName"

        params = {
            "serviceKey": config.MFDS_SERVICE_KEY,
            "type": "json",
            "pageNo": 1,
            "numOfRows": num_of_rows,
        }
        params[query_field] = query

        timeout = httpx.Timeout(config.MFDS_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)

        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVICE_UNAVAILABLE")

        payload = response.json()
        body = payload.get("body") or {}
        items = body.get("items") or []

        if isinstance(items, dict):
            return [items]
        if isinstance(items, list):
            return items
        return []

    # 식약처 DUR 품목정보 API 호출(e약은요 fallback) - REQ-DRUG-001, REQ-DRUG-005
    async def _request_dur_item_info(self, query: str, num_of_rows: int, query_field: str = "itemName") -> list[dict]:
        url = f"{config.MFDS_BASE_URL}/DURPrdlstInfoService03/getDurPrdlstInfoList03"
        if query_field not in {"itemName", "itemSeq"}:
            query_field = "itemName"

        params = {
            "serviceKey": config.MFDS_SERVICE_KEY,
            "type": "json",
            "pageNo": 1,
            "numOfRows": num_of_rows,
        }
        params[query_field] = query

        timeout = httpx.Timeout(config.MFDS_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)

        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="SERVICE_UNAVAILABLE")

        payload = response.json()
        body = payload.get("body") or {}
        items = body.get("items") or []

        if isinstance(items, dict):
            return [items]
        if isinstance(items, list):
            return items
        return []

    async def _resolve_item_seq_candidates_by_standard_code(self, standard_code: str) -> list[str]:
        if not standard_code:
            return []

        params = {
            "page": 1,
            "sort": "",
            "sortOrder": "false",
            "searchYn": "true",
            "searchDivision": "detail",
            "searchConEe": "AND",
            "searchConUd": "AND",
            "searchConNb": "AND",
            "stdrCodeName": standard_code,
        }
        timeout = httpx.Timeout(config.MFDS_TIMEOUT_SECONDS)

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.get(self._NEDRUG_SEARCH_URL, params=params)
            if response.status_code >= status.HTTP_400_BAD_REQUEST:
                return []
            return self._extract_item_seq_candidates_from_nedrug_html(response.text)
        except httpx.HTTPError:
            return []

    @classmethod
    def _extract_item_seq_candidates_from_nedrug_html(cls, html: str, limit: int = 5) -> list[str]:
        if not html:
            return []

        item_seqs: list[str] = []
        seen: set[str] = set()
        for matched in cls._NEDRUG_ITEM_SEQ_PATTERN.finditer(html):
            item_seq = matched.group(1).strip()
            if not item_seq or item_seq in seen:
                continue
            seen.add(item_seq)
            item_seqs.append(item_seq)
            if len(item_seqs) >= limit:
                break

        return item_seqs

    @staticmethod
    def _build_easy_drug_search_candidates(drug_name: str) -> list[tuple[str, str]]:
        normalized_query = str(drug_name or "").strip()
        if not normalized_query:
            return []

        candidates: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()

        digits_only = MfdsService._extract_digits(value=normalized_query)
        # 품목기준코드는 대체로 숫자 8~10자리
        if 8 <= len(digits_only) <= 10:
            item_seq_candidate = ("itemSeq", digits_only)
            candidates.append(item_seq_candidate)
            seen.add(item_seq_candidate)

        name_candidate = ("itemName", normalized_query)
        if name_candidate not in seen:
            candidates.append(name_candidate)

        return candidates

    @staticmethod
    def _prepend_item_seq_candidates(candidates: list[tuple[str, str]], item_seqs: list[str]) -> list[tuple[str, str]]:
        if not item_seqs:
            return candidates

        normalized_candidates = list(candidates)
        seen = set(normalized_candidates)
        prepend: list[tuple[str, str]] = []
        for item_seq in item_seqs:
            normalized_item_seq = str(item_seq or "").strip()
            if not normalized_item_seq:
                continue
            candidate = ("itemSeq", normalized_item_seq)
            if candidate in seen:
                continue
            seen.add(candidate)
            prepend.append(candidate)

        return prepend + normalized_candidates

    @staticmethod
    def _extract_digits(value: str) -> str:
        return re.sub(r"\D", "", str(value or ""))

    @classmethod
    def _looks_like_standard_code(cls, value: str) -> bool:
        digits = cls._extract_digits(value=value)
        return 12 <= len(digits) <= 14

    # 식약처 조회결과 캐시 저장 - REQ-DRUG-003
    async def _sync_drug_info_cache(self, items: list[dict]) -> None:
        expires_at = datetime.now(config.TIMEZONE) + timedelta(days=7)
        for item in items:
            item_seq = self._nullable_str(self._pick(item, "ITEM_SEQ", "itemSeq"))
            if not item_seq:
                continue

            defaults = {
                "drug_name_display": self._nullable_str(self._pick(item, "ITEM_NAME", "itemName")),
                "manufacturer": self._nullable_str(self._pick(item, "ENTP_NAME", "entpName")),
                "efficacy": self._nullable_str(self._pick(item, "EE_DOC_DATA", "efcyQesitm")),
                "dosage_info": self._nullable_str(self._pick(item, "UD_DOC_DATA", "useMethodQesitm")),
                "precautions": self._nullable_str(self._pick(item, "NB_DOC_DATA", "atpnQesitm", "atpnWarnQesitm")),
                "interactions": self._nullable_str(self._pick(item, "INTRC_QESITM", "intrcQesitm")),
                "side_effects": self._nullable_str(self._pick(item, "SE_QESITM", "seQesitm")),
                "storage_method": self._nullable_str(self._pick(item, "STORAGE_METHOD", "depositMethodQesitm")),
                "expires_at": expires_at,
            }

            existing_cache = await DrugInfoCache.get_or_none(mfds_item_seq=item_seq)
            if existing_cache:
                # 부분 데이터(DUR fallback) 동기화 시 기존 상세 텍스트를 None으로 덮어쓰지 않는다.
                update_payload: dict[str, object | None] = {"expires_at": defaults["expires_at"]}
                for field_name, field_value in defaults.items():
                    if field_name == "expires_at":
                        continue
                    if field_value is not None:
                        update_payload[field_name] = field_value
                await DrugInfoCache.filter(id=existing_cache.id).update(**update_payload)
                continue
            await DrugInfoCache.create(mfds_item_seq=item_seq, **defaults)

    @staticmethod
    def _nullable_str(value: object) -> str | None:
        if value is None:
            return None
        string_value = str(value).strip()
        return string_value or None

    @staticmethod
    def _pick(item: dict, *keys: str) -> object | None:
        for key in keys:
            if key in item and item.get(key) is not None:
                return item.get(key)
        return None
