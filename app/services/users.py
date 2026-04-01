from tortoise.transactions import in_transaction

from app.dtos.users import UserUpdateRequest
from app.models.domains.auth_entities import AuthAccount
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.auth import AuthService
from app.utils.common import normalize_phone_number


class UserManageService:
    def __init__(self):
        self.repo = UserRepository()
        self.auth_service = AuthService()

    async def _is_social_user(self, user: User) -> bool:
        """소셜 로그인 사용자인지 확인"""
        auth_account = await AuthAccount.filter(user_id=user.id).first()
        return auth_account is not None

    async def _is_social_generated_data(self, user: User) -> dict[str, bool]:
        """소셜 로그인으로 생성된 데이터인지 확인"""
        return {
            "email": user.email.endswith("@social.local"),
            "phone": user.phone_number.startswith("0")
            and len(user.phone_number) == 11
            and user.phone_number[1:].isdigit(),
        }

    async def update_user(self, user: User, data: UserUpdateRequest) -> User:
        is_social_user = await self._is_social_user(user)
        social_data_flags = await self._is_social_generated_data(user)

        # 이메일 검증 (소셜 사용자가 소셜 생성 이메일을 변경하려는 경우만 검증)
        if data.email:
            if not (is_social_user and social_data_flags["email"]):
                await self.auth_service.check_email_exists(data.email, exclude_user_id=user.id)

        # 전화번호 검증 (소셜 사용자가 소셜 생성 전화번호를 변경하려는 경우만 검증)
        if data.phone_number:
            if not (is_social_user and social_data_flags["phone"]):
                normalized_phone_number = normalize_phone_number(data.phone_number)
                await self.auth_service.check_phone_number_exists(normalized_phone_number, exclude_user_id=user.id)
                data.phone_number = normalized_phone_number
            else:
                # 소셜 사용자의 경우 전화번호 정규화만 수행
                data.phone_number = normalize_phone_number(data.phone_number)

        async with in_transaction():
            await self.repo.update_instance(user=user, data=data.model_dump(exclude_none=True))
            await user.refresh_from_db()
        return user
