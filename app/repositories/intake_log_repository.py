# app/repositories/intake_log_repository.py
from __future__ import annotations

from datetime import datetime

from app.models.schedules import IntakeLog


class IntakeLogRepository:
    async def list_logs_by_patient_and_range(
        self,
        patient_id: int,
        start_dt: datetime,
        end_dt: datetime,
    ) -> list[IntakeLog]:
        """
        특정 환자의 기간 내 복약 로그 조회
        """
        return await IntakeLog.filter(
            patient_id=patient_id,
            scheduled_at__gte=start_dt,
            scheduled_at__lt=end_dt,
        ).all()

    async def get_exact_log(
        self,
        schedule_id: int,
        schedule_time_id: int,
        scheduled_at: datetime,
    ) -> IntakeLog | None:
        """
        동일한 복약 슬롯(스케줄/시간/예약시각)에 해당하는 로그 1건 조회
        중복 체크 방지와 undo 대상 탐색에 사용
        """
        return await IntakeLog.get_or_none(
            schedule_id=schedule_id,
            schedule_time_id=schedule_time_id,
            scheduled_at=scheduled_at,
        )

    async def create_intake_log(
        self,
        *,
        patient_id: int,
        patient_med_id: int,
        schedule_id: int,
        schedule_time_id: int,
        scheduled_at: datetime,
        taken_at: datetime,
        status: str,
        note: str | None,
        recorded_by_user_id: int | None,
    ) -> IntakeLog:
        """
        복약 로그 생성
        """
        return await IntakeLog.create(
            patient_id=patient_id,
            patient_med_id=patient_med_id,
            schedule_id=schedule_id,
            schedule_time_id=schedule_time_id,
            scheduled_at=scheduled_at,
            taken_at=taken_at,
            status=status,
            note=note,
            recorded_by_user_id=recorded_by_user_id,
        )

    async def delete_log(
        self,
        log: IntakeLog,
    ) -> None:
        """
        복약 로그 삭제(undo)
        """
        await log.delete()
