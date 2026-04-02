from __future__ import annotations

from collections import deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request, status

from app.core import config

_RATE_LIMIT_STORE: dict[str, deque[float]] = {}
_RATE_LIMIT_LOCK = Lock()


def _client_ip(request: Request) -> str:
    forwarded_for = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded_for:
        return forwarded_for
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _check_rate_limit(*, bucket: str, key: str, max_requests: int, window_seconds: int) -> None:
    now = monotonic()
    threshold = now - window_seconds
    store_key = f"{bucket}:{key}"

    with _RATE_LIMIT_LOCK:
        timestamps = _RATE_LIMIT_STORE.setdefault(store_key, deque())
        while timestamps and timestamps[0] <= threshold:
            timestamps.popleft()
        if len(timestamps) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요.",
                },
            )
        timestamps.append(now)


async def limit_auth_login(request: Request) -> None:
    _check_rate_limit(
        bucket="auth-login",
        key=_client_ip(request),
        max_requests=max(1, int(config.AUTH_LOGIN_RATE_LIMIT_MAX_REQUESTS)),
        window_seconds=max(1, int(config.AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS)),
    )


async def limit_auth_refresh(request: Request) -> None:
    _check_rate_limit(
        bucket="auth-refresh",
        key=_client_ip(request),
        max_requests=max(1, int(config.AUTH_REFRESH_RATE_LIMIT_MAX_REQUESTS)),
        window_seconds=max(1, int(config.AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS)),
    )


async def limit_auth_password_reset(request: Request) -> None:
    _check_rate_limit(
        bucket="auth-password-reset",
        key=_client_ip(request),
        max_requests=max(1, int(config.AUTH_PASSWORD_RESET_RATE_LIMIT_MAX_REQUESTS)),
        window_seconds=max(1, int(config.AUTH_PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS)),
    )


def reset_rate_limit_store() -> None:
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_STORE.clear()
