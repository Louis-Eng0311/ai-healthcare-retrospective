import secrets
import string
from datetime import datetime, timedelta

from fastapi import HTTPException
from starlette import status
from tortoise.transactions import in_transaction

from app.core import config
from app.models.patients import CaregiverPatientLink, InvitationCode, Patient
from app.models.users import User
from app.services.role_utils import user_has_role


class InvitationService:
    async def _get_self_patient_for_invite(self, user: User, *, create_if_missing: bool) -> Patient:
        patient = await Patient.get_or_none(user_id=user.id)
        if not patient:
            patient = await Patient.get_or_none(user_id=user.id, owner_user_id=user.id)

        is_patient = await user_has_role(user.id, "PATIENT")
        if not is_patient and not patient:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        if not patient and create_if_missing:
            patient = await Patient.create(user_id=user.id, owner_user_id=user.id, display_name=user.name)

        if not patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="활성 초대코드가 없습니다.")

        return patient

    # 초대 코드 생성 - REQ-USER-004
    async def create_invite_code(self, user: User, expires_in_minutes: int) -> InvitationCode:
        patient = await self._get_self_patient_for_invite(user=user, create_if_missing=True)

        now = datetime.now(config.TIMEZONE)
        expires_at = now + timedelta(minutes=expires_in_minutes)
        await InvitationCode.filter(patient_id=patient.id, used_at__isnull=True).delete()

        alphabet = string.ascii_uppercase + string.digits
        for _ in range(10):
            code = "".join(secrets.choice(alphabet) for _ in range(10))
            is_duplicate = await InvitationCode.filter(code=code).exists()
            if not is_duplicate:
                return await InvitationCode.create(patient_id=patient.id, code=code, expires_at=expires_at)

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="INTERNAL_ERROR")

    # 초대 코드 폐기 - REQ-USER-004
    async def delete_invite_code(self, user: User) -> None:
        patient = await self._get_self_patient_for_invite(user=user, create_if_missing=False)

        deleted_count = await InvitationCode.filter(patient_id=patient.id, used_at__isnull=True).delete()
        if deleted_count == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

    # 초대 코드 연동 - REQ-USER-005
    async def link_by_invite_code(self, user: User, code: str) -> CaregiverPatientLink:
        is_caregiver = await user_has_role(user.id, "CAREGIVER", "GUARDIAN")
        if not is_caregiver:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        now = datetime.now(config.TIMEZONE)

        async with in_transaction() as conn:
            invite_code = await InvitationCode.filter(code=code).using_db(conn).first()
            if not invite_code:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
            if invite_code.used_at is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT")
            if invite_code.expires_at and invite_code.expires_at < now:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UNPROCESSABLE")

            existing_link = (
                await CaregiverPatientLink.filter(
                    caregiver_user_id=user.id,
                    patient_id=invite_code.patient_id,
                )
                .using_db(conn)
                .first()
            )

            if existing_link and existing_link.status == "active" and existing_link.revoked_at is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT")

            if existing_link:
                await (
                    CaregiverPatientLink.filter(id=existing_link.id)
                    .using_db(conn)
                    .update(
                        status="active",
                        revoked_at=None,
                    )
                )
                link = await CaregiverPatientLink.get(id=existing_link.id).using_db(conn)
            else:
                link = await CaregiverPatientLink.create(
                    caregiver_user_id=user.id,
                    patient_id=invite_code.patient_id,
                    status="active",
                    revoked_at=None,
                    using_db=conn,
                )

            marked = (
                await InvitationCode.filter(id=invite_code.id, used_at__isnull=True).using_db(conn).update(used_at=now)
            )
            if marked != 1:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT")

            return link

    # 연동 목록 조회 - REQ-USER-006
    async def get_links(self, user: User, *, mode: str | None = None) -> tuple[str, list[CaregiverPatientLink]]:
        is_caregiver = await user_has_role(user.id, "CAREGIVER", "GUARDIAN")
        is_patient = await user_has_role(user.id, "PATIENT")

        normalized_mode = (mode or "").strip().upper()

        if normalized_mode == "CAREGIVER":
            if not is_caregiver:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")
            links = (
                await CaregiverPatientLink.filter(
                    caregiver_user_id=user.id,
                    status="active",
                    revoked_at__isnull=True,
                )
                .select_related("patient__user", "caregiver_user")
                .order_by("-created_at")
            )
            return "CAREGIVER", links

        if normalized_mode == "PATIENT":
            patient = await Patient.get_or_none(user_id=user.id)
            if not patient:
                patient = await Patient.create(user_id=user.id, owner_user_id=user.id, display_name=user.name)

            links = (
                await CaregiverPatientLink.filter(
                    patient_id=patient.id,
                    status="active",
                    revoked_at__isnull=True,
                )
                .select_related("patient__user", "caregiver_user")
                .order_by("-created_at")
            )
            return "PATIENT", links

        if is_caregiver:
            links = (
                await CaregiverPatientLink.filter(
                    caregiver_user_id=user.id,
                    status="active",
                    revoked_at__isnull=True,
                )
                .select_related("patient__user", "caregiver_user")
                .order_by("-created_at")
            )
            return "CAREGIVER", links

        if is_patient:
            patient = await Patient.get_or_none(user_id=user.id)
            if not patient:
                patient = await Patient.create(user_id=user.id, owner_user_id=user.id, display_name=user.name)

            links = (
                await CaregiverPatientLink.filter(
                    patient_id=patient.id,
                    status="active",
                    revoked_at__isnull=True,
                )
                .select_related("patient__user", "caregiver_user")
                .order_by("-created_at")
            )
            return "PATIENT", links

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

    # 연동 해제 - REQ-USER-007
    async def unlink(self, user: User, link_id: int) -> CaregiverPatientLink:
        link = (
            await CaregiverPatientLink.filter(id=link_id)
            .select_related("patient", "patient__user", "caregiver_user")
            .first()
        )
        if not link:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        is_caregiver = await user_has_role(user.id, "CAREGIVER", "GUARDIAN")
        is_patient = await user_has_role(user.id, "PATIENT")

        allowed = False
        if is_caregiver and link.caregiver_user_id == user.id:
            allowed = True

        if is_patient:
            patient = await Patient.get_or_none(user_id=user.id)
            if patient and patient.id == link.patient_id:
                allowed = True

        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        if link.status != "active" or link.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="CONFLICT")

        now = datetime.now(config.TIMEZONE)
        await CaregiverPatientLink.filter(id=link.id).update(status="revoked", revoked_at=now)
        await link.refresh_from_db()
        return link
