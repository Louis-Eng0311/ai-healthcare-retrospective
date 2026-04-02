from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.dependencies.security import get_request_user
from app.dtos.chat import RequesterRole
from app.dtos.guide import (
    GuideDetailResponse,
    GuideGenerateRequest,
    GuideGenerateResponse,
    GuideListResponse,
    GuideRegenerateResponse,
)
from app.models.documents import Document
from app.models.patients import Patient
from app.models.users import User
from app.services.access_policy import assert_can_access_patient, resolve_requester_role
from app.services.guide import GuideService, GuideServiceError

guide_router = APIRouter(prefix="/guides", tags=["guides"])


# 서비스 예외를 HTTP 예외로 변환
def _raise_service_error(exc: GuideServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


# 문서 접근 권한 검사
async def _assert_can_access_document(*, requester: User, document_id: int) -> None:
    document = await Document.get_or_none(id=document_id, deleted_at=None)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "DOCUMENT_NOT_FOUND",
                "message": "문서를 찾을 수 없습니다.",
            },
        )

    patient_id = getattr(document, "patient_id", None)
    if patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DOCUMENT_PATIENT_MISSING",
                "message": "문서에 연결된 환자 정보가 없습니다.",
            },
        )

    await assert_can_access_patient(
        requester=requester,
        patient_id=int(patient_id),
    )


# 목록 조회 대상 환자 결정
async def _resolve_list_patient_id(*, requester: User, patient_id: int | None) -> int:
    role = await resolve_requester_role(int(requester.id))

    if role == RequesterRole.ADMIN:
        if patient_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "PATIENT_ID_REQUIRED",
                    "message": "patient_id가 필요합니다.",
                },
            )
        return int(patient_id)

    if role == RequesterRole.PATIENT:
        patient = await Patient.get_or_none(user_id=int(requester.id))
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "PATIENT_NOT_LINKED",
                    "message": "환자 정보가 연결되지 않았습니다.",
                },
            )
        return int(patient.id)

    if role == RequesterRole.CAREGIVER:
        if patient_id is None:
            own_patient = await Patient.get_or_none(user_id=int(requester.id))
            if own_patient:
                return int(own_patient.id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "PATIENT_ID_REQUIRED",
                    "message": "보호자 계정은 patient_id가 필요합니다.",
                },
            )
        await assert_can_access_patient(requester=requester, patient_id=int(patient_id))
        return int(patient_id)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "FORBIDDEN",
            "message": "권한이 없습니다.",
        },
    )


# 가이드 생성 요청
@guide_router.post(
    "/generate",
    response_model=GuideGenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_guide(
    req: GuideGenerateRequest,
    requester: User = Depends(get_request_user),
) -> GuideGenerateResponse:
    await _assert_can_access_document(
        requester=requester,
        document_id=req.document_id,
    )

    try:
        result = await GuideService.create_guide_generation(
            document_id=req.document_id,
            requester_user_id=int(requester.id),
        )
        return result
    except GuideServiceError as exc:
        _raise_service_error(exc)


# 가이드 목록 조회
@guide_router.get(
    "",
    response_model=GuideListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_guides(
    patient_id: int | None = Query(default=None, ge=1),
    requester: User = Depends(get_request_user),
) -> GuideListResponse:
    resolved_patient_id = await _resolve_list_patient_id(
        requester=requester,
        patient_id=patient_id,
    )

    try:
        result = await GuideService.list_guides(patient_id=resolved_patient_id)
        return result
    except GuideServiceError as exc:
        _raise_service_error(exc)


# 가이드 상세 조회
@guide_router.get(
    "/{guide_id}",
    response_model=GuideDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_guide_detail(
    guide_id: int = Path(..., ge=1),
    requester: User = Depends(get_request_user),
) -> GuideDetailResponse:
    try:
        result = await GuideService.get_guide_detail(guide_id=guide_id)
    except GuideServiceError as exc:
        _raise_service_error(exc)

    await assert_can_access_patient(
        requester=requester,
        patient_id=result.data.patient_id,
    )
    return result


# 가이드 재생성 요청
@guide_router.post(
    "/{guide_id}/regenerate",
    response_model=GuideRegenerateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def regenerate_guide(
    guide_id: int = Path(..., ge=1),
    requester: User = Depends(get_request_user),
) -> GuideRegenerateResponse:
    try:
        detail = await GuideService.get_guide_detail(guide_id=guide_id)
    except GuideServiceError as exc:
        _raise_service_error(exc)

    await assert_can_access_patient(
        requester=requester,
        patient_id=detail.data.patient_id,
    )

    try:
        result = await GuideService.regenerate_guide(
            guide_id=guide_id,
            requester_user_id=int(requester.id),
        )
        return result
    except GuideServiceError as exc:
        _raise_service_error(exc)
