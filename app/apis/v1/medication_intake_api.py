# app/apis/v1/medication_intake_api.py
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dtos.medication_intake_dtos import (
    AdherenceResponse,
    IntakeCheckRequest,
    IntakeCheckResponse,
    IntakeSkipRequest,
    IntakeSkipResponse,
    IntakeStatusResponse,
    IntakeUndoRequest,
    IntakeUndoResponse,
)
from app.services.medication_intake_service import MedicationIntakeService

# /api/v1 는 상위 router에서 이미 붙기 때문에
# 여기서는 복약 관련 세부 prefix만 선언한다.
router = APIRouter(prefix="/schedules", tags=["Medication"])


def get_service() -> MedicationIntakeService:
    return MedicationIntakeService()


MedicationServiceDep = Annotated[MedicationIntakeService, Depends(get_service)]
PatientIdQuery = Annotated[int, Query(..., description="환자 ID")]
DateFromQuery = Annotated[date, Query(..., alias="from", description="조회 시작일")]
DateToQuery = Annotated[date, Query(..., alias="to", description="조회 종료일")]


@router.post("/{schedule_id}/check", response_model=IntakeCheckResponse)
async def check_medication(
    schedule_id: int,
    request: IntakeCheckRequest,
    service: MedicationServiceDep,
) -> IntakeCheckResponse:
    """
    복약 완료 체크

    예시:
    POST /api/v1/schedules/12001/check

    body:
    {
      "schedule_time_id": 13001,
      "scheduled_date": "2026-03-10",
      "taken_at": "2026-03-10T08:02:00",
      "note": "식후 복용",
      "recorded_by_user_id": 9101
    }
    """
    return await service.check_medication(schedule_id, request)


@router.delete("/{schedule_id}/check", response_model=IntakeUndoResponse)
async def undo_medication(
    schedule_id: int,
    request: IntakeUndoRequest,
    service: MedicationServiceDep,
) -> IntakeUndoResponse:
    """
    복약 체크 취소(undo)

    같은 schedule_id + schedule_time_id + scheduled_date 슬롯에 대해
    저장되어 있는 intake_log 1건을 삭제한다.
    """
    return await service.undo_medication(schedule_id, request)


@router.get("/status", response_model=IntakeStatusResponse)
async def get_schedule_status(
    patient_id: PatientIdQuery,
    date_from: DateFromQuery,
    date_to: DateToQuery,
    service: MedicationServiceDep,
) -> IntakeStatusResponse:
    """
    기간 내 복약 현황 조회

    예시:
    GET /api/v1/schedules/status?patient_id=10001&from=2026-03-10&to=2026-03-12
    """
    return await service.get_patient_intake_status(patient_id, date_from, date_to)


@router.get("/adherence", response_model=AdherenceResponse)
async def get_schedule_adherence(
    patient_id: PatientIdQuery,
    date_from: DateFromQuery,
    date_to: DateToQuery,
    service: MedicationServiceDep,
) -> AdherenceResponse:
    """
    기간 내 복약 이행률 조회

    예시:
    GET /api/v1/schedules/adherence?patient_id=10001&from=2026-03-10&to=2026-03-12
    """
    return await service.get_patient_adherence(patient_id, date_from, date_to)


@router.post("/{schedule_id}/skip", response_model=IntakeSkipResponse)
async def skip_medication(
    schedule_id: int,
    request: IntakeSkipRequest,
    service: MedicationServiceDep,
) -> IntakeSkipResponse:
    return await service.skip_medication(schedule_id, request)
