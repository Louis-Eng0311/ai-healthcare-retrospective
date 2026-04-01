import re
from datetime import date, datetime

from app.core import config

ALLOWED_EMAIL_DOMAINS = {"gmail.com", "naver.com", "daum.net", "daum.com"}
SOCIAL_EMAIL_DOMAINS = {"social.local"}


def validate_email_format(email: str) -> str:
    """이메일 형식 검증 - 소셜 로그인 사용자 고려"""
    if not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise ValueError("유효하지 않은 이메일 형식입니다.")

    domain = email.rsplit("@", 1)[1].lower()

    # 소셜 로그인 도메인은 항상 허용
    if domain in SOCIAL_EMAIL_DOMAINS:
        return email

    # 일반 허용 도메인 검증
    if domain not in ALLOWED_EMAIL_DOMAINS:
        raise ValueError("지원하지 않는 이메일 도메인입니다. gmail.com, naver.com, daum.net만 사용 가능합니다.")

    return email


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("비밀번호는 8자 이상이어야 합니다.")

    if not re.search(r"[A-Z]", password):
        raise ValueError("비밀번호는 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.")

    if not re.search(r"[a-z]", password):
        raise ValueError("비밀번호는 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.")

    if not re.search(r"[0-9]", password):
        raise ValueError("비밀번호는 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.")

    if not re.search(r"[^a-zA-Z0-9]", password):
        raise ValueError("비밀번호는 대문자, 소문자, 숫자, 특수문자를 각각 1개 이상 포함해야 합니다.")

    return password


def validate_phone_number(phone_number: str) -> str:
    """전화번호 형식 검증 - 소셜 로그인 사용자 고려"""
    patterns = [
        r"010-\d{4}-\d{4}",  # 010-1234-5678
        r"010\d{8}",  # 01012345678
        r"\+8210\d{8}",  # +821012345678
        r"0\d{10}",  # 소셜 로그인으로 생성된 전화번호 (01234567890)
    ]

    if not any(re.fullmatch(p, phone_number) for p in patterns):
        raise ValueError("휴대폰 번호 형식이 올바르지 않습니다.")

    return phone_number


def validate_birthday(birthday: date | str) -> date:
    if isinstance(birthday, str):
        try:
            birthday = date.fromisoformat(birthday)
        except ValueError as e:
            raise ValueError("올바르지 않은 날짜 형식입니다. format: YYYY-MM-DD") from e

    today = datetime.now(tz=config.TIMEZONE).date()
    if birthday > today:
        raise ValueError("생년월일은 오늘 날짜보다 클 수 없습니다.")

    return birthday
