from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.security import get_request_user
from app.dtos.settings import UserSettingsResponse, UserSettingsUpdateRequest
from app.models.users import User
from app.services.settings import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])

CurrentUser = Annotated[User, Depends(get_request_user)]


@router.get("", response_model=UserSettingsResponse)
async def get_settings(current_user: CurrentUser) -> UserSettingsResponse:
    """사용자 설정 조회"""
    return await SettingsService.get_user_settings(current_user.id)


@router.patch("", response_model=UserSettingsResponse)
async def update_settings(
    request: UserSettingsUpdateRequest,
    current_user: CurrentUser,
) -> UserSettingsResponse:
    """사용자 설정 수정"""
    return await SettingsService.update_user_settings(current_user.id, request)
