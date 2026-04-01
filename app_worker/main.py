# app_worker/main.py
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from tortoise import Tortoise

from app.db.bootstrap import bootstrap_database
from app.db.databases import TORTOISE_ORM
from app.models.notifications import Notification
from app.services.hospital_schedule_notifications import (
    dispatch_due_hospital_schedule_notifications,
    now_kst_naive,
)
from app.services.medication_notifications import dispatch_due_medication_notifications

QUEUE_NAME = os.getenv("APP_WORKER_QUEUE", "notification_queue")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # docker 기준
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


async def handle_job(raw: str) -> None:
    """
    raw 예: {"type":"SEND_NOTIFICATION","notification_id":123}
    여기서는 "발송 처리 완료"를 DB에 기록한다.
    (현재 스키마에 status 컬럼이 없으므로 sent_at을 처리 완료 시각으로 사용)
    """
    try:
        job = json.loads(raw)
    except Exception:
        print(f"[app_worker] invalid job payload: {raw!r}")
        return

    print(f"[app_worker] received job: {job}")

    job_type = job.get("type")
    if job_type != "SEND_NOTIFICATION":
        print(f"[app_worker] unknown job type: {job_type!r}")
        return

    notification_id = job.get("notification_id")
    if not notification_id:
        print("[app_worker] missing notification_id")
        return

    # 1) DB에서 알림 조회
    notif = await Notification.get_or_none(id=int(notification_id))
    if not notif:
        print(f"[app_worker] notification not found: {notification_id}")
        return

    # 2) 중복 처리 방지: 이미 sent_at 있으면(처리 완료) 스킵
    if notif.sent_at is not None:
        print(f"[app_worker] already sent: {notification_id}")
        return

    # 3) 처리 완료 기록: sent_at 채우기 (UTC naive로 저장)
    notif.sent_at = datetime.now(UTC).replace(tzinfo=None)
    await notif.save(update_fields=["sent_at"])
    print(f"[app_worker] marked sent_at: {notification_id}")


async def main() -> None:
    # 1) DB 연결
    await Tortoise.init(config=TORTOISE_ORM)
    await bootstrap_database()
    print("[app_worker] tortoise initialized")

    r = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    try:
        await r.ping()
        print(f"[app_worker] connected redis {REDIS_HOST}:{REDIS_PORT}, queue={QUEUE_NAME}")
        last_schedule_check_at = now_kst_naive() - timedelta(minutes=1)

        while True:
            window_end = now_kst_naive()
            if window_end > last_schedule_check_at:
                try:
                    created = await dispatch_due_hospital_schedule_notifications(
                        window_start=last_schedule_check_at,
                        window_end=window_end,
                    )
                    if created:
                        print(f"[app_worker] created hospital schedule notifications: {created}")
                except Exception as exc:
                    print(f"[app_worker] failed to create hospital schedule notifications: {exc!r}")

                try:
                    created = await dispatch_due_medication_notifications(
                        window_start=last_schedule_check_at,
                        window_end=window_end,
                    )
                    if created:
                        print(f"[app_worker] created medication notifications: {created}")
                except Exception as exc:
                    print(f"[app_worker] failed to create medication notifications: {exc!r}")
                finally:
                    last_schedule_check_at = window_end

            item = await r.brpop(QUEUE_NAME, timeout=30)
            if item is None:
                continue
            _, raw = item
            await handle_job(raw)

    finally:
        await r.aclose()
        # ✅ 워커 종료 시 DB 연결 종료
        await Tortoise.close_connections()
        print("[app_worker] shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
