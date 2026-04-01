import asyncio
import json
import logging
import os
from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from tortoise import Tortoise

from ai_worker.tasks.generate_guide import generate_guide
from app.db.databases import TORTOISE_ORM
from app.models.guides import Guide, GuideStatus
from app.services.chat import ChatService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_URL = (os.getenv("REDIS_URL", "redis://localhost:6379/0") or "").strip()
GUIDE_QUEUE_NAME = (os.getenv("AI_WORKER_QUEUE", "ai_tasks") or "").strip()
CHAT_QUEUE_NAME = (os.getenv("CHAT_WORKER_QUEUE", "chat_tasks") or "").strip()

GUIDE_GENERATING_TIMEOUT_MINUTES = int((os.getenv("GUIDE_GENERATING_TIMEOUT_MINUTES", "30") or "30").strip())
STALE_GUIDE_CHECK_INTERVAL_SECONDS = int((os.getenv("STALE_GUIDE_CHECK_INTERVAL_SECONDS", "60") or "60").strip())


# DB 연결 초기화
async def _init_db() -> None:
    logger.info("worker: init db start")
    await Tortoise.init(config=TORTOISE_ORM)
    logger.info("worker: init db done")


# DB 연결 종료
async def _close_db() -> None:
    logger.info("worker: close db start")
    await Tortoise.close_connections()
    logger.info("worker: close db done")


# 30분 이상 GENERATING 상태인 가이드 실패 처리
async def _fail_stale_generating_guides() -> None:
    threshold = datetime.now(UTC) - timedelta(minutes=GUIDE_GENERATING_TIMEOUT_MINUTES)

    stale_guides = await Guide.filter(
        status=GuideStatus.GENERATING,
        created_at__lt=threshold,
    ).all()

    if not stale_guides:
        return

    for guide in stale_guides:
        guide.status = GuideStatus.FAILED
        guide.failure_code = "GUIDE_GENERATION_TIMEOUT"
        guide.failure_message = f"Guide generation exceeded {GUIDE_GENERATING_TIMEOUT_MINUTES} minutes."
        await guide.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])

    logger.warning("worker: marked %s stale generating guide(s) as FAILED", len(stale_guides))


# 주기적으로 stale guide 정리
async def _stale_guide_watchdog() -> None:
    logger.info(
        "worker: stale guide watchdog start timeout=%s min interval=%s sec",
        GUIDE_GENERATING_TIMEOUT_MINUTES,
        STALE_GUIDE_CHECK_INTERVAL_SECONDS,
    )

    while True:
        try:
            await _fail_stale_generating_guides()
        except Exception:
            logger.exception("worker: stale guide watchdog failed")

        await asyncio.sleep(STALE_GUIDE_CHECK_INTERVAL_SECONDS)


async def _handle_task(task: dict[str, object]) -> None:
    task_type = task.get("task")
    logger.info("worker: task_type=%s task=%s", task_type, task)

    if task_type == "generate_guide":
        guide_id = int(task["guide_id"])
        await generate_guide(guide_id)
        logger.info("worker: generate_guide done")
        return

    if task_type == "generate_chat_reply":
        await ChatService.generate_assistant_reply(
            session_id=int(task["session_id"]),
            user_message_id=int(task["user_message_id"]),
            assistant_message_id=int(task["assistant_message_id"]),
        )
        logger.info("worker: generate_chat_reply done")
        return

    logger.warning("worker: unknown task_type=%s", task_type)


async def _consume_queue(queue_name: str) -> None:
    logger.info("worker: consumer start queue=%s", queue_name)
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        while True:
            item = await client.brpop(queue_name, timeout=5)
            if not item:
                await asyncio.sleep(0.2)
                continue

            logger.info("worker: raw item received queue=%s item=%s", queue_name, item)
            _, raw = item
            try:
                task = json.loads(raw)
            except Exception:
                logger.exception("worker: invalid task json queue=%s", queue_name)
                continue

            try:
                await _handle_task(task)
            except Exception:
                logger.exception("worker: task failed queue=%s task=%s", queue_name, task)
    finally:
        await client.aclose()


async def worker_loop():
    logger.info("worker: loop start")
    logger.info("worker: REDIS_URL=%s", REDIS_URL)
    logger.info("worker: GUIDE_QUEUE_NAME=%s", GUIDE_QUEUE_NAME)
    logger.info("worker: CHAT_QUEUE_NAME=%s", CHAT_QUEUE_NAME)

    await _init_db()

    watchdog_task = asyncio.create_task(_stale_guide_watchdog())
    guide_consumer = asyncio.create_task(_consume_queue(GUIDE_QUEUE_NAME))
    chat_consumer = asyncio.create_task(_consume_queue(CHAT_QUEUE_NAME))

    try:
        await asyncio.gather(watchdog_task, guide_consumer, chat_consumer)
    finally:
        for task in (watchdog_task, guide_consumer, chat_consumer):
            task.cancel()
        await _close_db()


def main():
    asyncio.run(worker_loop())


if __name__ == "__main__":
    main()
