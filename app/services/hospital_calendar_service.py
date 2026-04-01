# app/services/hospital_calendar_service.py

from __future__ import annotations

from fastapi import HTTPException, status

from app.dtos.hospital_calendar_dtos import (
    HospitalScheduleCreateRequest,
    HospitalScheduleResponse,
    HospitalScheduleUpdateRequest,
)
from app.repositories.hospital_calendar_repository import HospitalCalendarRepository


class HospitalCalendarService:
    """
    병원 일정 Service

    현재는 팀프로젝트용 최소 CRUD 기준으로 작성
    추후 확장 가능:
    - 보호자/환자 권한 확인
    - owner_user / caregiver link 검증
    - 일정 중복 검증
    """

    def __init__(self, repository: HospitalCalendarRepository | None = None):
        self.repository = repository or HospitalCalendarRepository()

    async def create_schedule(
        self,
        request: HospitalScheduleCreateRequest,
        created_by_user_id: int | None = None,
    ) -> HospitalScheduleResponse:
        schedule = await self.repository.create(
            patient_id=request.patient_id,
            title=request.title,
            scheduled_at=request.scheduled_at,
            description=request.description,
            hospital_name=request.hospital_name,
            location=request.location,
            created_by_user_id=created_by_user_id,
        )
        return self._to_response(schedule)

    async def get_schedules(self, patient_id: int | None = None) -> list[HospitalScheduleResponse]:
        schedules = await self.repository.get_list(patient_id=patient_id)
        return [self._to_response(schedule) for schedule in schedules]

    async def update_schedule(
        self,
        schedule_id: int,
        request: HospitalScheduleUpdateRequest,
    ) -> HospitalScheduleResponse:
        schedule = await self.repository.get_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="병원 일정을 찾을 수 없습니다.",
            )

        updated_schedule = await self.repository.update(
            schedule,
            title=request.title,
            scheduled_at=request.scheduled_at,
            description=request.description,
            hospital_name=request.hospital_name,
            location=request.location,
        )
        return self._to_response(updated_schedule)

    async def delete_schedule(self, schedule_id: int) -> None:
        schedule = await self.repository.get_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="병원 일정을 찾을 수 없습니다.",
            )

        await self.repository.delete(schedule)

    @staticmethod
    def _to_response(schedule) -> HospitalScheduleResponse:
        return HospitalScheduleResponse(
            id=schedule.id,
            patient_id=schedule.patient_id,
            title=schedule.title,
            description=schedule.description,
            hospital_name=schedule.hospital_name,
            location=schedule.location,
            scheduled_at=schedule.scheduled_at,
            created_by_user_id=schedule.created_by_user_id,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
        )
