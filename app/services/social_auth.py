from datetime import date
from hashlib import sha1
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import HTTPException
from starlette import status

from app.core import config
from app.dtos.auth import LoginRole, SocialProvider
from app.models.healthcare import AuthAccount, Role, UserRole
from app.models.users import Gender, User
from app.repositories.user_repository import UserRepository


class SocialAuthService:
    def __init__(self):
        self.user_repo = UserRepository()

    def build_authorize_url(self, provider: SocialProvider, role: LoginRole) -> str:
        state = f"{role.value}:{uuid4().hex}"
        if provider == SocialProvider.KAKAO:
            if not config.KAKAO_CLIENT_ID:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Kakao client is not configured."
                )
            params = {
                "response_type": "code",
                "client_id": config.KAKAO_CLIENT_ID,
                "redirect_uri": config.KAKAO_REDIRECT_URI,
                "state": state,
            }
            return f"https://kauth.kakao.com/oauth/authorize?{urlencode(params)}"

        if not config.NAVER_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Naver client is not configured."
            )
        params = {
            "response_type": "code",
            "client_id": config.NAVER_CLIENT_ID,
            "redirect_uri": config.NAVER_REDIRECT_URI,
            "state": state,
        }
        return f"https://nid.naver.com/oauth2.0/authorize?{urlencode(params)}"

    async def exchange_code_and_fetch_profile(
        self, *, provider: SocialProvider, code: str, state: str | None = None
    ) -> dict[str, str | None]:
        access_token: str
        async with httpx.AsyncClient(timeout=10.0) as client:
            if provider == SocialProvider.KAKAO:
                token_payload = {
                    "grant_type": "authorization_code",
                    "client_id": config.KAKAO_CLIENT_ID,
                    "client_secret": config.KAKAO_CLIENT_SECRET,
                    "redirect_uri": config.KAKAO_REDIRECT_URI,
                    "code": code,
                }
                token_res = await client.post("https://kauth.kakao.com/oauth/token", data=token_payload)
                if token_res.status_code >= 400:
                    print(f"[KAKAO ERROR] status={token_res.status_code}, body={token_res.text}")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kakao token exchange failed.")
                token_data = token_res.json()
                access_token = token_data.get("access_token", "")
                if not access_token:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail="Kakao access token is missing."
                    )
                profile_res = await client.get(
                    "https://kapi.kakao.com/v2/user/me", headers={"Authorization": f"Bearer {access_token}"}
                )
                if profile_res.status_code >= 400:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kakao profile request failed.")
                profile_data = profile_res.json()
                kakao_account = profile_data.get("kakao_account") or {}
                properties = profile_data.get("properties") or {}
                return {
                    "provider_user_id": str(profile_data.get("id", "")) or None,
                    "email": kakao_account.get("email"),
                    "name": kakao_account.get("name") or properties.get("nickname") or "kakao-user",
                }

            token_params = {
                "grant_type": "authorization_code",
                "client_id": config.NAVER_CLIENT_ID,
                "client_secret": config.NAVER_CLIENT_SECRET,
                "code": code,
                "state": state or "",
            }
            token_res = await client.post("https://nid.naver.com/oauth2.0/token", params=token_params)
            if token_res.status_code >= 400:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Naver token exchange failed.")
            token_data = token_res.json()
            access_token = token_data.get("access_token", "")
            if not access_token:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Naver access token is missing.")
            profile_res = await client.get(
                "https://openapi.naver.com/v1/nid/me", headers={"Authorization": f"Bearer {access_token}"}
            )
            if profile_res.status_code >= 400:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Naver profile request failed.")
            profile_data = profile_res.json().get("response", {})
            return {
                "provider_user_id": profile_data.get("id"),
                "email": profile_data.get("email"),
                "name": profile_data.get("name") or "naver-user",
            }

    def resolve_role(self, requested_role: LoginRole | None, state: str | None) -> LoginRole:
        if requested_role is not None:
            return requested_role
        if state and ":" in state:
            role_prefix = state.split(":", 1)[0]
            try:
                return LoginRole(role_prefix)
            except ValueError:
                pass
        return LoginRole.PATIENT

    async def get_or_create_user_by_social(
        self,
        *,
        provider: SocialProvider,
        provider_user_id: str,
        email: str | None,
        name: str,
        current_user: User | None = None,
    ) -> User:
        auth_account = (
            await AuthAccount.filter(provider=provider.value, provider_user_id=provider_user_id)
            .select_related("user")
            .first()
        )
        if auth_account:
            if current_user and auth_account.user_id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="해당 소셜 계정은 이미 다른 사용자에 연결되어 있습니다.",
                )
            return auth_account.user

        if current_user is not None:
            await AuthAccount.create(user=current_user, provider=provider.value, provider_user_id=provider_user_id)
            return current_user

        user: User | None = None
        if email:
            user = await self.user_repo.get_user_by_email(email)

        if user is None:
            safe_email = email or await self._generate_fallback_email(provider, provider_user_id)
            safe_phone = await self._generate_fallback_phone(provider, provider_user_id)
            user = await self.user_repo.create_user(
                email=safe_email,
                hashed_password=None,
                name=name[:20] if name else f"{provider.value}-user",
                phone_number=safe_phone,
                gender=Gender.MALE,
                birthday=date(1970, 1, 1),
            )
            default_role, _ = await Role.get_or_create(
                code=LoginRole.PATIENT.value, defaults={"name": LoginRole.PATIENT.value}
            )
            await UserRole.get_or_create(user=user, role=default_role)

            from app.models.patients import Patient

            await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": user.name},
            )

        await AuthAccount.create(user=user, provider=provider.value, provider_user_id=provider_user_id)
        return user

    async def _generate_fallback_email(self, provider: SocialProvider, provider_user_id: str) -> str:
        seed = "".join(ch for ch in provider_user_id.lower() if ch.isalnum())
        local = f"{provider.value}_{seed}"[:28]
        email = f"{local}@social.local"
        if not await self.user_repo.exists_by_email(email):
            return email
        suffix = uuid4().hex[:6]
        return f"{local[:21]}_{suffix}@social.local"

    async def _generate_fallback_phone(self, provider: SocialProvider, provider_user_id: str) -> str:
        for idx in range(10):
            seed = f"{provider.value}:{provider_user_id}:{idx}"
            numeric = str(int(sha1(seed.encode("utf-8")).hexdigest(), 16))
            phone = f"0{numeric[:10]}"
            if not await self.user_repo.exists_by_phone_number(phone):
                return phone
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate phone number."
        )
