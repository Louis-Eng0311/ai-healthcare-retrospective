from datetime import date

from fastapi import HTTPException
from starlette import status
from tortoise.contrib.test import TestCase

from app.dtos.auth import SocialProvider
from app.models.healthcare import AuthAccount
from app.models.users import Gender, User
from app.repositories.user_repository import UserRepository
from app.services.social_auth import SocialAuthService


class TestSocialAuthService(TestCase):
    async def test_social_login_links_existing_local_user_by_email(self) -> None:
        repo = UserRepository()
        local_user = await repo.create_user(
            email="local_user@gmail.com",
            hashed_password="hashed-password",
            name="로컬유저",
            phone_number="01055556666",
            gender=Gender.MALE,
            birthday=date(1990, 1, 1),
        )

        resolved_user = await SocialAuthService().get_or_create_user_by_social(
            provider=SocialProvider.KAKAO,
            provider_user_id="kakao-uid-100",
            email="local_user@gmail.com",
            name="카카오유저",
        )

        assert resolved_user.id == local_user.id
        linked = await AuthAccount.get_or_none(provider="kakao", provider_user_id="kakao-uid-100")
        assert linked is not None
        assert linked.user_id == local_user.id

    async def test_social_login_links_to_current_user_when_logged_in(self) -> None:
        repo = UserRepository()
        current_user = await repo.create_user(
            email="current_user@gmail.com",
            hashed_password="hashed-password",
            name="현재유저",
            phone_number="01077778888",
            gender=Gender.FEMALE,
            birthday=date(1993, 3, 3),
        )
        await repo.create_user(
            email="other_user@gmail.com",
            hashed_password="hashed-password",
            name="다른유저",
            phone_number="01022223333",
            gender=Gender.MALE,
            birthday=date(1994, 4, 4),
        )

        resolved_user = await SocialAuthService().get_or_create_user_by_social(
            provider=SocialProvider.KAKAO,
            provider_user_id="kakao-uid-200",
            email="other_user@gmail.com",
            name="카카오유저",
            current_user=current_user,
        )

        assert resolved_user.id == current_user.id
        linked = await AuthAccount.get_or_none(provider="kakao", provider_user_id="kakao-uid-200")
        assert linked is not None
        assert linked.user_id == current_user.id
        assert await User.all().count() == 2

    async def test_social_login_conflict_when_social_account_linked_to_other_user(self) -> None:
        repo = UserRepository()
        owner_user = await repo.create_user(
            email="owner_user@gmail.com",
            hashed_password="hashed-password",
            name="소유유저",
            phone_number="01011110000",
            gender=Gender.FEMALE,
            birthday=date(1989, 9, 9),
        )
        current_user = await repo.create_user(
            email="current_user2@gmail.com",
            hashed_password="hashed-password",
            name="현재유저2",
            phone_number="01099990000",
            gender=Gender.MALE,
            birthday=date(1991, 1, 1),
        )
        await AuthAccount.create(user=owner_user, provider="kakao", provider_user_id="kakao-uid-300")

        try:
            await SocialAuthService().get_or_create_user_by_social(
                provider=SocialProvider.KAKAO,
                provider_user_id="kakao-uid-300",
                email="owner_user@gmail.com",
                name="카카오유저",
                current_user=current_user,
            )
        except HTTPException as exc:
            assert exc.status_code == status.HTTP_409_CONFLICT
            return

        raise AssertionError("409 conflict was expected but not raised")
