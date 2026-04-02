from __future__ import annotations

from fastapi import HTTPException, status

from app.dtos.chat import RequesterRole
from app.models.patients import CaregiverPatientLink, Patient
from app.models.users import User
from app.services.role_utils import user_has_role


async def resolve_requester_role(user_id: int) -> RequesterRole:
    if await user_has_role(user_id, "ADMIN"):
        return RequesterRole.ADMIN
    if await user_has_role(user_id, "CAREGIVER", "GUARDIAN"):
        return RequesterRole.CAREGIVER
    if await user_has_role(user_id, "PATIENT"):
        return RequesterRole.PATIENT

    patient_exists = await Patient.filter(user_id=user_id).exists()
    if patient_exists:
        return RequesterRole.PATIENT
    return RequesterRole.ADMIN


async def assert_can_access_patient(*, requester: User, patient_id: int) -> None:
    role = await resolve_requester_role(int(requester.id))
    patient = await Patient.get_or_none(id=patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "PATIENT_NOT_FOUND",
                "message": "환자 정보를 찾을 수 없습니다.",
            },
        )

    if role == RequesterRole.ADMIN:
        return

    if role == RequesterRole.PATIENT:
        if patient.user_id != int(requester.id) and patient.owner_user_id != int(requester.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "본인 환자 정보에만 접근할 수 있습니다.",
                },
            )
        return

    if role == RequesterRole.CAREGIVER:
        if patient.user_id == int(requester.id) or patient.owner_user_id == int(requester.id):
            return
        linked = await CaregiverPatientLink.filter(
            caregiver_user_id=int(requester.id),
            patient_id=patient_id,
            status="active",
        ).exists()
        if not linked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "FORBIDDEN",
                    "message": "연결된 환자 정보에만 접근할 수 있습니다.",
                },
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "FORBIDDEN",
            "message": "권한이 없습니다.",
        },
    )
