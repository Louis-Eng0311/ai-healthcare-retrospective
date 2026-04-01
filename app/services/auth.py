from fastapi.exceptions import HTTPException
from pydantic import EmailStr
from starlette import status
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.dtos.auth import LoginRequest, LoginRole, SignUpRequest
from app.models.healthcare import Role, UserRole
from app.models.patients import Patient
from app.models.users import User
from app.repositories.user_repository import UserRepository
from app.services.jwt import JwtService
from app.utils.common import normalize_phone_number
from app.utils.jwt.tokens import AccessToken, RefreshToken
from app.utils.security import hash_password, verify_password


class AuthService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.jwt_service = JwtService()

    async def signup(self, data: SignUpRequest) -> User:
        # 이메일 중복 체크
        await self.check_email_exists(data.email)

        # 입력받은 휴대폰 번호를 노말라이즈
        normalized_phone_number = normalize_phone_number(data.phone_number)

        # 휴대폰 번호 중복 체크
        await self.check_phone_number_exists(normalized_phone_number)

        # 유저 생성
        async with in_transaction():
            user = await self.user_repo.create_user(
                email=data.email,
                hashed_password=hash_password(data.password),  # 해시화된 비밀번호를 사용
                name=data.name,
                phone_number=normalized_phone_number,
                gender=data.gender,
                birthday=data.birth_date,
            )
            # 기본 역할은 PATIENT, 회원가입 시 역할 선택 가능하도록 수정
            role_code = getattr(data, "role", LoginRole.PATIENT.value)
            role_codes = [LoginRole.PATIENT.value]
            if role_code in {LoginRole.CAREGIVER.value, LoginRole.GUARDIAN.value}:
                role_codes.append(LoginRole.CAREGIVER.value)
            elif role_code == LoginRole.ADMIN.value:
                role_codes = [LoginRole.ADMIN.value]

            for code in role_codes:
                role, _ = await Role.get_or_create(code=code, defaults={"name": code})
                await UserRole.get_or_create(user=user, role=role)

            if LoginRole.PATIENT.value in role_codes:
                await Patient.get_or_create(
                    user_id=user.id,
                    defaults={"display_name": user.name, "owner_user_id": user.id},
                )

            return user

    async def authenticate(self, data: LoginRequest) -> User:
        # 이메일로 사용자 조회
        email = str(data.email)
        user = await self.user_repo.get_user_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        # 비밀번호 검증
        if not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="이메일 또는 비밀번호가 올바르지 않습니다."
            )

        # 활성 사용자 체크
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="비활성화된 계정입니다.")

        return user

    async def login(self, user: User, *, role: LoginRole) -> dict[str, AccessToken | RefreshToken]:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="비활성화된 계정입니다.")
        requested_role = role.value
        role_candidates = self._role_candidates(role)
        role_assigned = (
            await UserRole.filter(user_id=user.id)
            .filter(Q(role__name__in=role_candidates) | Q(role__code__in=role_candidates))
            .exists()
        )
        if not role_assigned:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="선택한 역할로 로그인할 수 없습니다.")
        return self.jwt_service.issue_jwt_pair(user, extra_claims={"login_role": requested_role})

    async def check_email_exists(self, email: str | EmailStr, *, exclude_user_id: int | None = None) -> None:
        if await self.user_repo.exists_by_email(email, exclude_user_id=exclude_user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 이메일입니다.")

    async def check_phone_number_exists(self, phone_number: str, *, exclude_user_id: int | None = None) -> None:
        if await self.user_repo.exists_by_phone_number(phone_number, exclude_user_id=exclude_user_id):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 휴대폰 번호입니다.")

    @staticmethod
    def _role_candidates(role: LoginRole) -> list[str]:
        if role == LoginRole.ADMIN:
            return [LoginRole.ADMIN.value]
        if role == LoginRole.GUARDIAN:
            return [LoginRole.GUARDIAN.value, LoginRole.CAREGIVER.value]
        if role == LoginRole.CAREGIVER:
            return [LoginRole.CAREGIVER.value, LoginRole.GUARDIAN.value]
        return [LoginRole.PATIENT.value]

    async def find_email(self, name: str, phone_number: str) -> str:
        normalized_phone = normalize_phone_number(phone_number)
        user = await self.user_repo.get_user_by_name_and_phone(name, normalized_phone)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="일치하는 사용자를 찾을 수 없습니다.")
        return user.email

    async def reset_password(self, email: str, name: str, phone_number: str, new_password: str) -> None:
        normalized_phone = normalize_phone_number(phone_number)
        user = await self.user_repo.get_user_by_email_name_phone(email, name, normalized_phone)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="일치하는 사용자를 찾을 수 없습니다.")
        await self.user_repo.update_instance(user, {"hashed_password": hash_password(new_password)})
