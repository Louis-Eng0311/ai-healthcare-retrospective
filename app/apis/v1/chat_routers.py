from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.dependencies.security import get_request_user
from app.dtos.chat import (
    ChatFeedbackCreateRequest,
    ChatFeedbackCreateResponse,
    ChatMessageCreateRequest,
    ChatMessageCreateResponse,
    ChatMessageListResponse,
    ChatSessionCreateRequest,
    ChatSessionCreateResponse,
    RequesterRole,
)
from app.models.chat import ChatSession
from app.models.patients import CaregiverPatientLink, Patient
from app.models.users import User
from app.services.chat import ChatService, ChatServiceError, _resolve_requester_role

chat_router = APIRouter(prefix="/chat", tags=["chat"])


# 서비스 예외를 HTTP 예외로 변환
def _raise_service_error(exc: ChatServiceError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
        },
    )


# 환자 접근 권한 검사
async def _assert_can_access_patient(*, requester: User, patient_id: int) -> None:
    role = await _resolve_requester_role(int(requester.id))
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


# 세션 접근 권한 검사
async def _assert_can_access_session(*, requester: User, session_id: int) -> ChatSession:
    session = await ChatSession.get_or_none(id=session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CHAT_SESSION_NOT_FOUND",
                "message": "채팅 세션을 찾을 수 없습니다.",
            },
        )

    patient_id = getattr(session, "patient_id", None)
    if patient_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "CHAT_SESSION_PATIENT_MISSING",
                "message": "세션에 연결된 환자 정보가 없습니다.",
            },
        )

    await _assert_can_access_patient(requester=requester, patient_id=int(patient_id))
    return session


# 세션 생성
@chat_router.post(
    "/sessions",
    response_model=ChatSessionCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    req: ChatSessionCreateRequest,
    requester: User = Depends(get_request_user),
) -> ChatSessionCreateResponse:
    await _assert_can_access_patient(
        requester=requester,
        patient_id=req.patient_id,
    )

    try:
        return await ChatService.create_session(
            requester=requester,
            patient_id=req.patient_id,
            mode=req.mode,
        )
    except ChatServiceError as exc:
        _raise_service_error(exc)


# 메시지 전송
@chat_router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_message(
    session_id: int = Path(..., ge=1),
    req: ChatMessageCreateRequest = ...,
    requester: User = Depends(get_request_user),
) -> ChatMessageCreateResponse:
    await _assert_can_access_session(
        requester=requester,
        session_id=session_id,
    )

    try:
        return await ChatService.create_message(
            requester=requester,
            session_id=session_id,
            content=req.content,
        )
    except ChatServiceError as exc:
        _raise_service_error(exc)


# 메시지 목록 조회
@chat_router.get(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_chat_messages(
    session_id: int = Path(..., ge=1),
    requester: User = Depends(get_request_user),
) -> ChatMessageListResponse:
    await _assert_can_access_session(
        requester=requester,
        session_id=session_id,
    )

    try:
        return await ChatService.list_messages(session_id=session_id)
    except ChatServiceError as exc:
        _raise_service_error(exc)


@chat_router.post(
    "/sessions/{session_id}/feedback",
    response_model=ChatFeedbackCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_feedback(
    session_id: int = Path(..., ge=1),
    req: ChatFeedbackCreateRequest = ...,
    requester: User = Depends(get_request_user),
) -> ChatFeedbackCreateResponse:
    await _assert_can_access_session(
        requester=requester,
        session_id=session_id,
    )

    try:
        return await ChatService.create_feedback(
            requester=requester,
            session_id=session_id,
            assistant_message_id=req.assistant_message_id,
            helpful=req.helpful,
            feedback_type=req.feedback_type,
            comment=req.comment,
        )
    except ChatServiceError as exc:
        _raise_service_error(exc)
