from __future__ import annotations

import os


def _env_str(name: str, default: str) -> str:
    return (os.getenv(name, default) or default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env_str(name, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = _env_str(name, str(default))
    try:
        return float(raw)
    except ValueError:
        return default


CHAT_DISCLAIMER = "본 답변은 의료 자문이 아닌 참고용 정보입니다."
CHAT_HISTORY_TURNS = _env_int("CHAT_HISTORY_TURNS", 8)
CHAT_MAX_MESSAGE_CHARS = _env_int("CHAT_MAX_MESSAGE_CHARS", 2000)
REDIS_URL = _env_str("REDIS_URL", "redis://localhost:6379/0")
CHAT_WORKER_QUEUE = _env_str("CHAT_WORKER_QUEUE", "chat_tasks")
CHAT_SLOW_REPLY_SECONDS = _env_float("CHAT_SLOW_REPLY_SECONDS", 3.0)
CHAT_SLOW_CONTEXT_SECONDS = _env_float("CHAT_SLOW_CONTEXT_SECONDS", 1.5)

