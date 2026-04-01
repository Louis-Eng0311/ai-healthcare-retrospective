# app/repositories/hospital_calendar_repository.py

from __future__ import annotations

from datetime import datetime

from app.models.hospital_schedules import HospitalSchedule


class HospitalCalendarRepository:
    """
    병원 일정 Repository

    역할:
    - DB 접근만 담당
    - 비즈니스 로직은 service 에서 처리
    """

    async def create(
        self,
        *,
        patient_id: int,
        title: str,
        scheduled_at: datetime,
        description: str | None = None,
        hospital_name: str | None = None,
        location: str | None = None,
        created_by_user_id: int | None = None,
    ) -> HospitalSchedule:
        return await HospitalSchedule.create(
            patient_id=patient_id,
            title=title,
            scheduled_at=scheduled_at,
            description=description,
            hospital_name=hospital_name,
            location=location,
            created_by_user_id=created_by_user_id,
        )

    async def get_by_id(self, schedule_id: int) -> HospitalSchedule | None:
        return await HospitalSchedule.get_or_none(id=schedule_id)

    async def get_list(self, *, patient_id: int | None = None) -> list[HospitalSchedule]:
        query = HospitalSchedule.all()

        if patient_id is not None:
            query = query.filter(patient_id=patient_id)

        return await query.order_by("scheduled_at")

    async def update(
        self,
        schedule: HospitalSchedule,
        *,
        title: str | None = None,
        scheduled_at: datetime | None = None,
        description: str | None = None,
        hospital_name: str | None = None,
        location: str | None = None,
    ) -> HospitalSchedule:
        """
        값이 들어온 필드만 부분 수정
        """
        if title is not None:
            schedule.title = title

        if scheduled_at is not None:
            schedule.scheduled_at = scheduled_at

        if description is not None:
            schedule.description = description

        if hospital_name is not None:
            schedule.hospital_name = hospital_name

        if location is not None:
            schedule.location = location

        await schedule.save()
        return schedule

    async def delete(self, schedule: HospitalSchedule) -> None:
        await schedule.delete()
