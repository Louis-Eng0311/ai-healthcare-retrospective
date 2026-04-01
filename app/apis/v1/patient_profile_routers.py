from __future__ import annotations

# app/apis/v1/patient_profile_routers.py
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import ORJSONResponse, Response

from app.dependencies.security import get_request_user
from app.dtos.notifications import ApiResponse
from app.dtos.patient_profile import PatientProfileOut, PatientProfileUpsertIn
from app.models.users import User
from app.services.patient_profile_service import (
    create_linked_patient_profile,
    create_my_patient_profile,
    delete_linked_patient_profile,
    delete_my_patient_profile,
    get_linked_patient_profile,
    get_my_patient_profile,
    update_linked_patient_profile,
    update_my_patient_profile,
)

router = APIRouter(prefix="/users", tags=["patient_profile"])


# ------------------------------------------------------------
# success/data 공통 응답 envelope 를 만드는 함수
# ------------------------------------------------------------
def _ok(data, status_code: int = status.HTTP_200_OK) -> ORJSONResponse:
    return ORJSONResponse(
        content=ApiResponse(data=data).model_dump(),
        status_code=status_code,
    )


# ------------------------------------------------------------
# 환자 본인 건강 프로필 조회 API
# ------------------------------------------------------------
@router.get("/me/health-profile", response_model=ApiResponse[PatientProfileOut], status_code=status.HTTP_200_OK)
async def api_get_my_health_profile(
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await get_my_patient_profile(user)
    return _ok(data)


# ------------------------------------------------------------
# 환자 본인 건강 프로필 등록 API
# ------------------------------------------------------------
@router.post("/me/health-profile", response_model=ApiResponse[PatientProfileOut], status_code=status.HTTP_201_CREATED)
async def api_create_my_health_profile(
    payload: PatientProfileUpsertIn,
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await create_my_patient_profile(user, payload)
    return _ok(data, status.HTTP_201_CREATED)


# ------------------------------------------------------------
# 환자 본인 건강 프로필 수정 API
# ------------------------------------------------------------
@router.patch("/me/health-profile", response_model=ApiResponse[PatientProfileOut], status_code=status.HTTP_200_OK)
async def api_patch_my_health_profile(
    payload: PatientProfileUpsertIn,
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await update_my_patient_profile(user, payload)
    return _ok(data)


# ------------------------------------------------------------
# 환자 본인 건강 프로필 삭제 API (soft delete)
# ------------------------------------------------------------
@router.delete("/me/health-profile", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_my_health_profile(
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    await delete_my_patient_profile(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 조회 API
# ------------------------------------------------------------
@router.get(
    "/links/{link_id}/health-profile", response_model=ApiResponse[PatientProfileOut], status_code=status.HTTP_200_OK
)
async def api_get_link_health_profile(
    link_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await get_linked_patient_profile(user, link_id)
    return _ok(data)


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 등록 API
# ------------------------------------------------------------
@router.post(
    "/links/{link_id}/health-profile",
    response_model=ApiResponse[PatientProfileOut],
    status_code=status.HTTP_201_CREATED,
)
async def api_create_link_health_profile(
    link_id: int,
    payload: PatientProfileUpsertIn,
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await create_linked_patient_profile(user, link_id, payload)
    return _ok(data, status.HTTP_201_CREATED)


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 수정 API
# ------------------------------------------------------------
@router.patch(
    "/links/{link_id}/health-profile", response_model=ApiResponse[PatientProfileOut], status_code=status.HTTP_200_OK
)
async def api_patch_link_health_profile(
    link_id: int,
    payload: PatientProfileUpsertIn,
    user: Annotated[User, Depends(get_request_user)],
) -> ORJSONResponse:
    data = await update_linked_patient_profile(user, link_id, payload)
    return _ok(data)


# ------------------------------------------------------------
# 보호자 연동 복약자 건강 프로필 삭제 API (soft delete)
# ------------------------------------------------------------
@router.delete("/links/{link_id}/health-profile", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_link_health_profile(
    link_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    await delete_linked_patient_profile(user, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
