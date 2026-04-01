# app/services/queue_service.py
from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

QUEUE_NAME = "notification_queue"


def get_redis() -> Redis:
    return Redis(host="redis", port=6379, decode_responses=True)


async def enqueue_notification_job(payload: dict[str, Any]) -> None:
    redis = get_redis()
    raw = json.dumps(payload, ensure_ascii=False)
    try:
        print(f"[queue] LPUSH -> {QUEUE_NAME}: {raw}")
        n = await redis.lpush(QUEUE_NAME, raw)
        print(f"[queue] LPUSH OK. queue_length={n}")
    except Exception as e:
        print(f"[queue] LPUSH FAILED: {e!r}")
        raise
    finally:
        await redis.aclose()


async def enqueue_send_notification(notification_id: int) -> None:
    await enqueue_notification_job({"type": "SEND_NOTIFICATION", "notification_id": notification_id})
