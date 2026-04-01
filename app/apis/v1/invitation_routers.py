from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import ORJSONResponse as Response

from app.dependencies.security import get_request_user
from app.dtos.invitation import (
    InviteCodeCreateRequest,
    InviteCodeCreateResponse,
    LinkByInviteCodeRequest,
    LinkByInviteCodeResponse,
    LinkListItemResponse,
    LinkListResponse,
    UnlinkResponse,
)
from app.models.users import User
from app.services.invitation import InvitationService

invitation_router = APIRouter(prefix="/users", tags=["users"])


# 초대 코드 생성 - REQ-USER-004
@invitation_router.post("/invite-code", response_model=InviteCodeCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_invite_code(
    payload: InviteCodeCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
    invitation_service: Annotated[InvitationService, Depends(InvitationService)],
) -> Response:
    invite_code = await invitation_service.create_invite_code(user=user, expires_in_minutes=payload.expires_in_minutes)
    return Response(
        InviteCodeCreateResponse.model_validate(invite_code).model_dump(),
        status_code=status.HTTP_201_CREATED,
    )


# 초대 코드 폐기 - REQ-USER-004
@invitation_router.delete("/invite-code", status_code=status.HTTP_200_OK)
async def delete_invite_code(
    user: Annotated[User, Depends(get_request_user)],
    invitation_service: Annotated[InvitationService, Depends(InvitationService)],
) -> Response:
    await invitation_service.delete_invite_code(user=user)
    return Response({"detail": "초대코드가 폐기되었습니다."}, status_code=status.HTTP_200_OK)


# 초대 코드 연동 - REQ-USER-005
@invitation_router.post("/link", response_model=LinkByInviteCodeResponse, status_code=status.HTTP_201_CREATED)
async def link_by_invite_code(
    payload: LinkByInviteCodeRequest,
    user: Annotated[User, Depends(get_request_user)],
    invitation_service: Annotated[InvitationService, Depends(InvitationService)],
) -> Response:
    link = await invitation_service.link_by_invite_code(user=user, code=payload.code)
    response = LinkByInviteCodeResponse(
        link_id=link.id,
        patient_id=link.patient_id,
        status=link.status,
        linked_at=link.created_at,
    )
    return Response(response.model_dump(), status_code=status.HTTP_201_CREATED)


# 연동 목록 조회 - REQ-USER-006
@invitation_router.get("/links", response_model=LinkListResponse, status_code=status.HTTP_200_OK)
async def get_links(
    user: Annotated[User, Depends(get_request_user)],
    invitation_service: Annotated[InvitationService, Depends(InvitationService)],
    mode: Annotated[str | None, Query()] = None,
) -> Response:
    role, links = await invitation_service.get_links(user=user, mode=mode)
    response_items = []

    for link in links:
        patient_name = link.patient.display_name
        if not patient_name and link.patient.user:
            patient_name = link.patient.user.name

        response_items.append(
            LinkListItemResponse(
                link_id=link.id,
                patient_id=link.patient_id,
                patient_user_id=link.patient.user_id,
                patient_name=patient_name,
                caregiver_user_id=link.caregiver_user_id,
                caregiver_name=link.caregiver_user.name,
                status=link.status,
                linked_at=link.created_at,
                revoked_at=link.revoked_at,
            )
        )

    response = LinkListResponse(role=role, links=response_items)
    return Response(response.model_dump(), status_code=status.HTTP_200_OK)


# 연동 해제 - REQ-USER-007
@invitation_router.delete("/links/{link_id}", response_model=UnlinkResponse, status_code=status.HTTP_200_OK)
async def unlink(
    link_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    invitation_service: Annotated[InvitationService, Depends(InvitationService)],
) -> Response:
    link = await invitation_service.unlink(user=user, link_id=link_id)
    response = UnlinkResponse(link_id=link.id, status=link.status, revoked_at=link.revoked_at)
    return Response(response.model_dump(), status_code=status.HTTP_200_OK)
