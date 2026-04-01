from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import ORJSONResponse as Response

from app.core import config
from app.dependencies.security import get_request_user
from app.dtos.users import UserDeviceCountResponse, UserDeviceRegisterRequest, UserInfoResponse, UserUpdateRequest
from app.models.healthcare import AuthAccount, UserRole
from app.models.notifications import UserDevice
from app.models.patients import Patient
from app.models.users import User
from app.services.users import UserManageService

user_router = APIRouter(prefix="/users", tags=["users"])


@user_router.get("/me", response_model=UserInfoResponse, status_code=status.HTTP_200_OK)
async def user_me_info(
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    patient = await Patient.get_or_none(user_id=user.id)

    response_data = UserInfoResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        phone_number=user.phone_number,
        birthday=user.birthday,
        gender=user.gender,
        created_at=user.created_at,
        patient_id=patient.id if patient else None,
    )

    return Response(response_data.model_dump(), status_code=status.HTTP_200_OK)


@user_router.patch("/me", response_model=UserInfoResponse, status_code=status.HTTP_200_OK)
async def update_user_me_info(
    update_data: UserUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    user_manage_service: Annotated[UserManageService, Depends(UserManageService)],
) -> Response:
    updated_user = await user_manage_service.update_user(user=user, data=update_data)
    patient = await Patient.get_or_none(user_id=updated_user.id)

    response_data = UserInfoResponse(
        id=updated_user.id,
        name=updated_user.name,
        email=updated_user.email,
        phone_number=updated_user.phone_number,
        birthday=updated_user.birthday,
        gender=updated_user.gender,
        created_at=updated_user.created_at,
        patient_id=patient.id if patient else None,
    )

    return Response(response_data.model_dump(), status_code=status.HTTP_200_OK)


@user_router.delete("/me", status_code=status.HTTP_200_OK)
async def withdraw_user(
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    user.is_active = False
    await user.save()
    await UserRole.filter(user_id=user.id).delete()
    await AuthAccount.filter(user_id=user.id).delete()
    resp = Response(content={"detail": "회원 탈퇴가 완료되었습니다."}, status_code=status.HTTP_200_OK)
    resp.delete_cookie(key="refresh_token", path="/")
    return resp


@user_router.post("/me/devices/register", response_model=UserDeviceCountResponse, status_code=status.HTTP_200_OK)
async def register_user_device(
    payload: UserDeviceRegisterRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> Response:
    device_id = payload.device_id.strip()
    if not device_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

    platform = payload.platform.strip() if payload.platform else None
    if platform == "":
        platform = None
    now = datetime.now(config.TIMEZONE)

    existing_device = await UserDevice.get_or_none(user_id=user.id, push_token=device_id)
    if existing_device:
        await UserDevice.filter(id=existing_device.id).update(
            platform=platform,
            is_active=True,
            created_at=now,
        )
    else:
        await UserDevice.create(
            user_id=user.id,
            platform=platform,
            push_token=device_id,
            is_active=True,
            created_at=now,
        )

    linked_device_count = await UserDevice.filter(user_id=user.id, is_active=True).count()
    last_login_device = await UserDevice.filter(user_id=user.id, is_active=True).order_by("-created_at").first()
    response_data = UserDeviceCountResponse(
        linked_device_count=linked_device_count,
        last_login_at=last_login_device.created_at if last_login_device else None,
    )
    return Response(response_data.model_dump(), status_code=status.HTTP_200_OK)
