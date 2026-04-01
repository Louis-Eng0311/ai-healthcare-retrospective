from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

_MFDS_SERVICE_KEY = (os.getenv("MFDS_SERVICE_KEY", "") or "").replace("\r", "").strip()

# 제품 허가정보
_PRODUCT_INFO_URL = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService06/getDrugPrdtPrmsnDtlInq04"
# e약은요
_EASY_DRUG_URL = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
# DUR 품목정보
_DUR_ITEM_URL = "https://apis.data.go.kr/1471000/DURPrdlstInfoService03/getDurPrdlstInfoList03"
# DUR 성분정보
_DUR_INGREDIENT_URL = "https://apis.data.go.kr/1471000/DURIrdntInfoService03/getDURIrdntInfoList03"
# 성분별 1일 최대 투여량
_MAX_DAILY_DOSE_URL = "https://apis.data.go.kr/1471000/DayMaxDosgQyByIngdService/getDayMaxDosgQyByIngdInq"


def normalize_drug_name(drug_name: str) -> str:
    name = (drug_name or "").strip()
    name = html.unescape(name)

    # 괄호/대괄호 내부 제거
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"\[.*?\]", " ", name)

    # 용량 제거
    name = re.sub(r"\d+(\.\d+)?\s*(mg|ml|g|mcg|㎎|㎖|그램)", " ", name, flags=re.IGNORECASE)

    # 남은 숫자 제거
    name = re.sub(r"\d+", " ", name)

    # 제형 제거
    name = re.sub(
        r"(tablet|tab|cap|capsule|softcap|soft capsule|정|캡슐|연질캡슐|필름코팅정|서방정|산|시럽|주사액|주사제)",
        " ",
        name,
        flags=re.IGNORECASE,
    )

    # 특수문자 정리
    name = re.sub(r"[/,+\-]", " ", name)

    # 공백 정리
    name = re.sub(r"\s+", " ", name).strip()

    return name


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


def _first_nonempty(*values: Any) -> str:
    for v in values:
        s = _clean_text(v)
        if s:
            return s
    return ""


def _safe_get(obj: dict[str, Any], *keys: str) -> str:
    for k in keys:
        if k in obj and obj[k] is not None:
            s = _clean_text(obj[k])
            if s:
                return s
    return ""


def _truncate(s: str, limit: int = 220) -> str:
    s = _clean_text(s)
    if len(s) <= limit:
        return s
    return s[:limit].rstrip() + "…"


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    cur = payload
    if "response" in cur and isinstance(cur["response"], dict):
        cur = cur["response"]

    if "body" in cur and isinstance(cur["body"], dict):
        cur = cur["body"]

    items = cur.get("items")
    if items is None:
        return []

    if isinstance(items, dict) and "item" in items:
        items = items["item"]

    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    if isinstance(items, dict):
        return [items]

    return []


async def _get_json(url: str, params: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


@dataclass
class MFDSEasyDrugInfo:
    item_name: str = ""
    entp_name: str = ""
    item_seq: str = ""
    efcy_qesitm: str = ""
    use_method_qesitm: str = ""
    atpn_warn_qesitm: str = ""
    atpn_qesitm: str = ""
    intrc_qesitm: str = ""
    se_qesitm: str = ""
    deposit_method_qesitm: str = ""


@dataclass
class MFDSProductInfo:
    item_name: str = ""
    entp_name: str = ""
    item_seq: str = ""
    prduct_type: str = ""
    material_name: str = ""
    storage_method: str = ""
    chart: str = ""


@dataclass
class MFDSDurItemInfo:
    item_name: str = ""
    item_seq: str = ""
    age_taboo: str = ""
    oldman_care: str = ""
    pregnant_taboo: str = ""
    combo_taboo: str = ""
    dose_care: str = ""
    period_care: str = ""
    efficacy_group_overlap: str = ""


@dataclass
class MFDSDurIngredientInfo:
    ingredient_name: str = ""
    age_taboo: str = ""
    oldman_care: str = ""
    pregnant_taboo: str = ""
    combo_taboo: str = ""
    dose_care: str = ""
    period_care: str = ""
    efficacy_group_overlap: str = ""


@dataclass
class MFDSMaxDailyDoseInfo:
    ingredient_name: str = ""
    max_daily_dose: str = ""
    unit: str = ""
    route: str = ""
    dosage_form: str = ""


@dataclass
class MFDSDrugBundle:
    query_name: str
    product_info: MFDSProductInfo | None
    easy_info: MFDSEasyDrugInfo | None
    dur_item_info: MFDSDurItemInfo | None
    dur_ingredient_info: MFDSDurIngredientInfo | None = None
    max_daily_dose_info: MFDSMaxDailyDoseInfo | None = None

    def to_prompt_block(self) -> str:
        lines: list[str] = [f"[약물 근거 요약] {_clean_text(self.query_name)}"]

        if self.product_info:
            p = self.product_info
            lines.append(
                "- 제품 정보: "
                + " / ".join(
                    [
                        x
                        for x in [
                            _truncate(p.item_name, 80),
                            _truncate(p.entp_name, 60),
                            _truncate(p.material_name, 120),
                            _truncate(p.prduct_type, 40),
                        ]
                        if x
                    ]
                )
            )
            if p.storage_method:
                lines.append(f"- 저장방법: {_truncate(p.storage_method, 120)}")

        if self.easy_info:
            e = self.easy_info
            if e.efcy_qesitm:
                lines.append(f"- 효능/효과: {_truncate(e.efcy_qesitm, 180)}")
            if e.use_method_qesitm:
                lines.append(f"- 사용법: {_truncate(e.use_method_qesitm, 180)}")
            caution = _first_nonempty(e.atpn_warn_qesitm, e.atpn_qesitm)
            if caution:
                lines.append(f"- 주의사항: {_truncate(caution, 180)}")
            if e.intrc_qesitm:
                lines.append(f"- 상호작용: {_truncate(e.intrc_qesitm, 180)}")
            if e.se_qesitm:
                lines.append(f"- 부작용: {_truncate(e.se_qesitm, 160)}")
            if e.deposit_method_qesitm:
                lines.append(f"- 보관법: {_truncate(e.deposit_method_qesitm, 120)}")

        dur_bits: list[str] = []

        if self.dur_item_info:
            d = self.dur_item_info
            if d.age_taboo:
                dur_bits.append(f"연령금기={_truncate(d.age_taboo, 80)}")
            if d.oldman_care:
                dur_bits.append(f"노인주의={_truncate(d.oldman_care, 80)}")
            if d.pregnant_taboo:
                dur_bits.append(f"임부금기={_truncate(d.pregnant_taboo, 80)}")
            if d.combo_taboo:
                dur_bits.append(f"병용금기={_truncate(d.combo_taboo, 80)}")
            if d.dose_care:
                dur_bits.append(f"용량주의={_truncate(d.dose_care, 80)}")
            if d.period_care:
                dur_bits.append(f"투여기간주의={_truncate(d.period_care, 80)}")
            if d.efficacy_group_overlap:
                dur_bits.append(f"효능군중복주의={_truncate(d.efficacy_group_overlap, 80)}")

        if self.dur_ingredient_info:
            d = self.dur_ingredient_info
            if d.age_taboo:
                dur_bits.append(f"연령금기={_truncate(d.age_taboo, 80)}")
            if d.oldman_care:
                dur_bits.append(f"노인주의={_truncate(d.oldman_care, 80)}")
            if d.pregnant_taboo:
                dur_bits.append(f"임부금기={_truncate(d.pregnant_taboo, 80)}")
            if d.combo_taboo:
                dur_bits.append(f"병용금기={_truncate(d.combo_taboo, 80)}")
            if d.dose_care:
                dur_bits.append(f"용량주의={_truncate(d.dose_care, 80)}")
            if d.period_care:
                dur_bits.append(f"투여기간주의={_truncate(d.period_care, 80)}")
            if d.efficacy_group_overlap:
                dur_bits.append(f"효능군중복주의={_truncate(d.efficacy_group_overlap, 80)}")

        if dur_bits:
            lines.append("- DUR 안전성 정보: " + " / ".join(dur_bits))

        if self.max_daily_dose_info:
            m = self.max_daily_dose_info
            dose_text = " / ".join([x for x in [m.max_daily_dose, m.unit, m.route, m.dosage_form] if x])
            if dose_text:
                lines.append(f"- 1일 최대투여량: {_truncate(dose_text, 120)}")

        return "\n".join(lines)

    def to_guide_dict(self) -> dict[str, Any]:
        product = self.product_info
        easy = self.easy_info
        dur_item = self.dur_item_info
        dur_ingredient = self.dur_ingredient_info
        max_dose = self.max_daily_dose_info

        precautions = _first_nonempty(
            easy.atpn_warn_qesitm if easy else "",
            easy.atpn_qesitm if easy else "",
        )

        contraindications = [
            x
            for x in [
                dur_item.age_taboo if dur_item else "",
                dur_item.pregnant_taboo if dur_item else "",
                dur_item.combo_taboo if dur_item else "",
                dur_ingredient.age_taboo if dur_ingredient else "",
                dur_ingredient.pregnant_taboo if dur_ingredient else "",
                dur_ingredient.combo_taboo if dur_ingredient else "",
            ]
            if _clean_text(x)
        ]

        return {
            "query_name": self.query_name,
            "drug_name_display": easy.item_name if easy and easy.item_name else (product.item_name if product else ""),
            "manufacturer": easy.entp_name if easy and easy.entp_name else (product.entp_name if product else ""),
            "ingredients": product.material_name if product else "",
            "efficacy": easy.efcy_qesitm if easy else "",
            "dosage_info": easy.use_method_qesitm if easy else "",
            "precautions": precautions,
            "interactions": easy.intrc_qesitm if easy else "",
            "side_effects": easy.se_qesitm if easy else "",
            "storage_method": _first_nonempty(
                easy.deposit_method_qesitm if easy else "",
                product.storage_method if product else "",
            ),
            "contraindications": contraindications,
            "dur_safety": {
                "age_taboo": _first_nonempty(
                    dur_item.age_taboo if dur_item else "",
                    dur_ingredient.age_taboo if dur_ingredient else "",
                ),
                "oldman_care": _first_nonempty(
                    dur_item.oldman_care if dur_item else "",
                    dur_ingredient.oldman_care if dur_ingredient else "",
                ),
                "pregnant_taboo": _first_nonempty(
                    dur_item.pregnant_taboo if dur_item else "",
                    dur_ingredient.pregnant_taboo if dur_ingredient else "",
                ),
                "combo_taboo": _first_nonempty(
                    dur_item.combo_taboo if dur_item else "",
                    dur_ingredient.combo_taboo if dur_ingredient else "",
                ),
                "dose_care": _first_nonempty(
                    dur_item.dose_care if dur_item else "",
                    dur_ingredient.dose_care if dur_ingredient else "",
                ),
                "period_care": _first_nonempty(
                    dur_item.period_care if dur_item else "",
                    dur_ingredient.period_care if dur_ingredient else "",
                ),
                "efficacy_group_overlap": _first_nonempty(
                    dur_item.efficacy_group_overlap if dur_item else "",
                    dur_ingredient.efficacy_group_overlap if dur_ingredient else "",
                ),
            },
            "max_daily_dose": {
                "ingredient_name": max_dose.ingredient_name if max_dose else "",
                "max_daily_dose": max_dose.max_daily_dose if max_dose else "",
                "unit": max_dose.unit if max_dose else "",
                "route": max_dose.route if max_dose else "",
                "dosage_form": max_dose.dosage_form if max_dose else "",
            },
        }


class MFDSClient:
    def __init__(self, service_key: str | None = None):
        self.service_key = (service_key or _MFDS_SERVICE_KEY or "").strip()

    def is_enabled(self) -> bool:
        return bool(self.service_key) and self.service_key != "__"

    async def search_product_info(self, drug_name: str) -> MFDSProductInfo | None:
        if not self.is_enabled():
            return None

        candidates = [normalize_drug_name(drug_name), _clean_text(drug_name)]
        seen: set[str] = set()

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            params = {
                "serviceKey": self.service_key,
                "type": "json",
                "pageNo": 1,
                "numOfRows": 5,
                "item_name": candidate,
            }

            try:
                payload = await _get_json(_PRODUCT_INFO_URL, params)
                items = _extract_items(payload)
                if not items:
                    continue
                item = items[0]
                return MFDSProductInfo(
                    item_name=_safe_get(item, "ITEM_NAME", "itemName", "품목명"),
                    entp_name=_safe_get(item, "ENTP_NAME", "entpName", "업체명"),
                    item_seq=_safe_get(item, "ITEM_SEQ", "itemSeq", "품목기준코드"),
                    prduct_type=_safe_get(item, "PRDUCT_TYPE", "prductType", "제형"),
                    material_name=_safe_get(item, "MATERIAL_NAME", "materialName", "주성분"),
                    storage_method=_safe_get(item, "STORAGE_METHOD", "storageMethod", "저장방법"),
                    chart=_safe_get(item, "CHART", "chart", "성상"),
                )
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    continue
                continue
            except httpx.HTTPError:
                continue

        return None

    async def search_easy_drug_info(self, drug_name: str) -> MFDSEasyDrugInfo | None:
        if not self.is_enabled():
            return None

        candidates = [normalize_drug_name(drug_name), _clean_text(drug_name)]
        seen: set[str] = set()

        for candidate in candidates:
            candidate = candidate.strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)

            params = {
                "ServiceKey": self.service_key,
                "type": "json",
                "pageNo": 1,
                "numOfRows": 5,
                "itemName": candidate,
            }

            try:
                payload = await _get_json(_EASY_DRUG_URL, params)
                items = _extract_items(payload)
                if not items:
                    continue
                item = items[0]
                return MFDSEasyDrugInfo(
                    item_name=_safe_get(item, "itemName", "ITEM_NAME"),
                    entp_name=_safe_get(item, "entpName", "ENTP_NAME"),
                    item_seq=_safe_get(item, "itemSeq", "ITEM_SEQ"),
                    efcy_qesitm=_safe_get(item, "efcyQesitm"),
                    use_method_qesitm=_safe_get(item, "useMethodQesitm"),
                    atpn_warn_qesitm=_safe_get(item, "atpnWarnQesitm"),
                    atpn_qesitm=_safe_get(item, "atpnQesitm"),
                    intrc_qesitm=_safe_get(item, "intrcQesitm"),
                    se_qesitm=_safe_get(item, "seQesitm"),
                    deposit_method_qesitm=_safe_get(item, "depositMethodQesitm"),
                )
            except httpx.HTTPError:
                continue

        return None

    async def search_dur_item_info(self, *, drug_name: str = "", item_seq: str = "") -> MFDSDurItemInfo | None:
        if not self.is_enabled():
            return None

        params_base: dict[str, Any] = {
            "serviceKey": self.service_key,
            "type": "json",
            "pageNo": 1,
            "numOfRows": 5,
        }

        candidates: list[dict[str, Any]] = []
        if item_seq:
            candidates.append({"itemSeq": item_seq})
        if drug_name:
            normalized = normalize_drug_name(drug_name)
            original = _clean_text(drug_name)
            if normalized:
                candidates.append({"itemName": normalized})
            if original and original != normalized:
                candidates.append({"itemName": original})

        if not candidates:
            return None

        seen: set[tuple[tuple[str, str], ...]] = set()

        for extra in candidates:
            key = tuple(sorted((k, str(v)) for k, v in extra.items()))
            if key in seen:
                continue
            seen.add(key)

            params = {**params_base, **extra}

            try:
                payload = await _get_json(_DUR_ITEM_URL, params)
                items = _extract_items(payload)
                if not items:
                    continue
                item = items[0]
                return MFDSDurItemInfo(
                    item_name=_safe_get(item, "ITEM_NAME", "itemName"),
                    item_seq=_safe_get(item, "ITEM_SEQ", "itemSeq"),
                    age_taboo=_safe_get(item, "AGE_TABOO", "ageTaboo", "AGE_TABOO_INFO", "ageTabooInfo"),
                    oldman_care=_safe_get(item, "OLDMAN_CARE", "oldmanCare", "OLDMAN_CARE_INFO", "oldmanCareInfo"),
                    pregnant_taboo=_safe_get(
                        item, "PREGNANT_TABOO", "pregnantTaboo", "PREGNANT_TABOO_INFO", "pregnantTabooInfo"
                    ),
                    combo_taboo=_safe_get(item, "COMBO_TABOO", "comboTaboo", "COMBO_TABOO_INFO", "comboTabooInfo"),
                    dose_care=_safe_get(item, "DOSE_CARE", "doseCare", "DOSE_CARE_INFO", "doseCareInfo"),
                    period_care=_safe_get(item, "PERIOD_CARE", "periodCare", "PERIOD_CARE_INFO", "periodCareInfo"),
                    efficacy_group_overlap=_safe_get(
                        item,
                        "EFFICACY_GROUP_OVERLAP",
                        "efficacyGroupOverlap",
                        "EFFECT_DUPL_CARE",
                        "effectDuplCare",
                    ),
                )
            except httpx.HTTPError:
                continue

        return None

    async def search_dur_ingredient_info(self, ingredient_name: str) -> MFDSDurIngredientInfo | None:
        if not self.is_enabled():
            return None

        normalized = normalize_drug_name(ingredient_name)
        if not normalized:
            return None

        params = {
            "serviceKey": self.service_key,
            "type": "json",
            "pageNo": 1,
            "numOfRows": 5,
            "ingrName": normalized,
        }

        try:
            payload = await _get_json(_DUR_INGREDIENT_URL, params)
            items = _extract_items(payload)
            if not items:
                return None
            item = items[0]
            return MFDSDurIngredientInfo(
                ingredient_name=_safe_get(item, "INGR_NAME", "ingrName", "성분명"),
                age_taboo=_safe_get(item, "AGE_TABOO", "ageTaboo", "AGE_TABOO_INFO", "ageTabooInfo"),
                oldman_care=_safe_get(item, "OLDMAN_CARE", "oldmanCare", "OLDMAN_CARE_INFO", "oldmanCareInfo"),
                pregnant_taboo=_safe_get(
                    item, "PREGNANT_TABOO", "pregnantTaboo", "PREGNANT_TABOO_INFO", "pregnantTabooInfo"
                ),
                combo_taboo=_safe_get(item, "COMBO_TABOO", "comboTaboo", "COMBO_TABOO_INFO", "comboTabooInfo"),
                dose_care=_safe_get(item, "DOSE_CARE", "doseCare", "DOSE_CARE_INFO", "doseCareInfo"),
                period_care=_safe_get(item, "PERIOD_CARE", "periodCare", "PERIOD_CARE_INFO", "periodCareInfo"),
                efficacy_group_overlap=_safe_get(
                    item,
                    "EFFICACY_GROUP_OVERLAP",
                    "efficacyGroupOverlap",
                    "EFFECT_DUPL_CARE",
                    "effectDuplCare",
                ),
            )
        except httpx.HTTPError:
            return None

    async def search_max_daily_dose(self, ingredient_name: str) -> MFDSMaxDailyDoseInfo | None:
        if not self.is_enabled():
            return None

        normalized = normalize_drug_name(ingredient_name)
        if not normalized:
            return None

        params = {
            "serviceKey": self.service_key,
            "type": "json",
            "pageNo": 1,
            "numOfRows": 5,
            "ingrKorName": normalized,
        }

        try:
            payload = await _get_json(_MAX_DAILY_DOSE_URL, params)
            items = _extract_items(payload)
            if not items:
                return None
            item = items[0]
            return MFDSMaxDailyDoseInfo(
                ingredient_name=_safe_get(item, "INGR_KOR_NAME", "ingrKorName", "성분명"),
                max_daily_dose=_safe_get(item, "DAY_MAX_DOSG_QY", "dayMaxDosgQy", "1일최대투여량"),
                unit=_safe_get(item, "UNIT", "unit", "단위"),
                route=_safe_get(item, "ROUTE", "route", "투여경로"),
                dosage_form=_safe_get(item, "FORM_NAME", "formName", "제형명"),
            )
        except httpx.HTTPError:
            return None

    async def fetch_drug_bundle(self, drug_name: str) -> MFDSDrugBundle:
        normalized_name = normalize_drug_name(drug_name)

        # 주력 소스: e약은요
        easy = await self.search_easy_drug_info(normalized_name or drug_name)

        item_seq = ""
        if easy and easy.item_seq:
            item_seq = easy.item_seq

        # DUR 품목정보
        dur_item = await self.search_dur_item_info(drug_name=normalized_name or drug_name, item_seq=item_seq)

        # 제품허가정보 optional fallback
        product = await self.search_product_info(normalized_name or drug_name)

        ingredient_name = ""
        if product and product.material_name:
            ingredient_name = product.material_name

        dur_ingredient = None
        max_daily_dose = None
        if ingredient_name:
            dur_ingredient = await self.search_dur_ingredient_info(ingredient_name)
            max_daily_dose = await self.search_max_daily_dose(ingredient_name)

        return MFDSDrugBundle(
            query_name=normalized_name or _clean_text(drug_name),
            product_info=product,
            easy_info=easy,
            dur_item_info=dur_item,
            dur_ingredient_info=dur_ingredient,
            max_daily_dose_info=max_daily_dose,
        )

    async def fetch_guide_drug_info(self, drug_name: str) -> dict[str, Any]:
        bundle = await self.fetch_drug_bundle(drug_name)
        return bundle.to_guide_dict()
