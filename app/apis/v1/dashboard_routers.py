from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies.security import get_request_user
from app.dtos.dashboard import DashboardResponse
from app.models.users import User
from app.services.dashboard import DashboardService
from app.services.role_utils import user_has_role

dashboard_router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@dashboard_router.get("", response_model=DashboardResponse)
async def get_dashboard(
    current_user: Annotated[User, Depends(get_request_user)],
    period: int = Query(7, ge=1, le=30, description="조회 기간 (일)"),
) -> DashboardResponse:
    """관리자 대시보드 데이터 조회 (ADMIN 역할만 허용)"""
    if not await user_has_role(current_user.id, "ADMIN"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자만 접근할 수 있습니다.")
    return await DashboardService.get_dashboard_data(period_days=period)
