from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

"""
[AH-HP-UTILS-v2]
- 목적: 건강프로필 입력 정규화/계산 유틸
- 사용처:
  - app/services/patient_profile_service.py
  - app/dtos/patient_profile.py (validator에서 필요 시 호출 가능)ㄴ
  - "몰라/모름/잘모르겠음" -> None
  - "없음/해당없음" -> 0
- 주의:
  - from __future__ import ... 는 파일 최상단에 있어야 함 (SyntaxError 방지)
"""

# -----------------------
# 공통: 문자열 판정
# -----------------------
_UNKNOWN_SET = {"모름", "몰라", "잘모르겠음", "unknown", "unk", "na", "n/a", "null"}
_NONE0_SET = {"없음", "해당없음", "없어요", "해당 없음", "해당-없음"}


def _is_blank_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() == ""


def _normalize_unknown_token(s: str) -> str:
    return s.strip().lower().replace(" ", "")


# -----------------------
# 공통: Decimal 변환
# -----------------------
def _to_decimal(v: Any) -> Decimal | None:
    """
    [각주] 숫자 계열 입력을 Decimal로 변환
    - "몰라/모름/잘모르겠음" -> None
    - "없음/해당없음" -> Decimal("0")
    - 변환 불가 문자열 -> None (서비스/DTO에서 422로 막고 싶으면 별도 검증에서 ValueError로 처리)
    """
    if v is None:
        return None

    if isinstance(v, Decimal):
        return v

    if isinstance(v, bool):
        # bool은 int로 취급되므로 여기서 차단
        return None

    if isinstance(v, (int, float)):
        return Decimal(str(v))

    if isinstance(v, str):
        raw = v.strip()
        if raw == "":
            return None

        key = _normalize_unknown_token(raw)

        # "모름" 계열 -> None
        if key in {_normalize_unknown_token(x) for x in _UNKNOWN_SET}:
            return None

        # "없음" 계열 -> 0
        if key in {_normalize_unknown_token(x) for x in _NONE0_SET}:
            return Decimal("0")

        # 숫자 문자열 파싱
        try:
            return Decimal(raw)
        except (InvalidOperation, ValueError):
            return None

    return None


def round_1(v: Any) -> Decimal | None:
    """
    [각주] 소수점 1자리 반올림 표준화
    - 키/몸무게/BMI/수면시간/흡연(갑)/음주(병) 등에 사용
    """
    d = _to_decimal(v)
    if d is None:
        return None
    try:
        return d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def round_0(v: Any) -> int | None:
    """
    [각주] 분(minute) 같은 정수형 입력 표준화
    - "없음/해당없음" -> 0
    - "모름" -> None
    - 실수면 반올림해서 int
    """
    d = _to_decimal(v)
    if d is None:
        return None
    try:
        return int(d.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        return None


# -----------------------
# 성별 normalize
# -----------------------
def normalize_sex(v: Any) -> str | None:
    """
    [각주] 성별 입력 normalize
    - 저장 표준: "MALE" / "FEMALE"
    - 모름/해당없음/빈값: None
    - 그 외(예: "중성", "기타")는 ValueError -> router에서 422로 변환해 "이렇게 입력" 안내
    """
    if v is None or _is_blank_str(v):
        return None

    if isinstance(v, str):
        s = v.strip()
        key = _normalize_unknown_token(s)

        # 무응답/모름/없음
        if key in {_normalize_unknown_token(x) for x in _UNKNOWN_SET.union(_NONE0_SET)}:
            return None

        # 남성
        if key in {"m", "male", "man", "남", "남자", "남성"}:
            return "MALE"

        # 여성
        if key in {"f", "female", "woman", "여", "여자", "여성"}:
            return "FEMALE"

        raise ValueError('sex는 "남/여" 또는 "M/F"로 입력해주세요. (예: "남", "여", "M", "F")')

    return None


# -----------------------
# BMI
# -----------------------
def calc_bmi(height_cm: Any, weight_kg: Any) -> Decimal | None:
    """
    [각주] BMI = kg / (m^2)
    - 입력이 "없음/해당없음"이면 0으로 들어오지만, BMI는 의미 없으니 None 처리
    - height, weight 둘 중 하나라도 None이면 None
    """
    h = _to_decimal(height_cm)
    w = _to_decimal(weight_kg)

    if h is None or w is None:
        return None
    if h <= 0 or w <= 0:
        return None

    h_m = h / Decimal("100")
    bmi = w / (h_m * h_m)
    return round_1(bmi)


# -----------------------
# meds list <-> json string
# -----------------------
def dumps_str_list(v: Any) -> str | None:
    """
    [각주] meds(list[str]) -> JSON 문자열로 저장
    - None/빈값 -> None
    - 문자열 1개 -> [문자열]
    """
    if v is None or _is_blank_str(v):
        return None

    if isinstance(v, str):
        v = [v]

    if not isinstance(v, list):
        return None

    cleaned: list[str] = []
    for x in v:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            cleaned.append(s)

    return json.dumps(cleaned, ensure_ascii=False)


def loads_str_list(v: Any) -> list[str]:
    """
    [각주] JSON 문자열 -> list[str]
    - None/빈값/깨진 JSON -> []
    """
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x is not None]

    s = str(v).strip()
    if s == "":
        return []

    try:
        data = json.loads(s)
        if isinstance(data, list):
            return [str(x) for x in data if x is not None]
        return []
    except Exception:
        return []
