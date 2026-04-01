from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.responses import JSONResponse as Response

from app.core import config
from app.core.config import Env
from app.dtos.auth import (
    FindEmailRequest,
    FindEmailResponse,
    LoginRequest,
    LoginResponse,
    LoginRole,
    ResetPasswordRequest,
    SignUpRequest,
    SocialLoginStartResponse,
    SocialProvider,
    TokenRefreshResponse,
)
from app.services.auth import AuthService
from app.services.jwt import JwtService
from app.services.social_auth import SocialAuthService

auth_router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_domain() -> str | None:
    domain = (config.COOKIE_DOMAIN or "").strip() or None
    if not domain:
        return None
    if domain in {"localhost", "127.0.0.1"}:
        return None
    return domain


def _build_login_response(tokens: dict, login_role: LoginRole) -> Response:
    resp = Response(
        content=LoginResponse(access_token=str(tokens["access_token"]), login_role=login_role).model_dump(),
        status_code=status.HTTP_200_OK,
    )
    _set_refresh_cookie(resp, tokens)
    return resp


def _set_refresh_cookie(resp: Response | RedirectResponse, tokens: dict) -> None:
    refresh_exp = None
    try:
        refresh_exp = tokens["refresh_token"].payload.get("exp")
    except Exception:
        refresh_exp = None

    resp.set_cookie(
        key="refresh_token",
        value=str(tokens["refresh_token"]),
        httponly=True,
        secure=True if config.ENV == Env.PROD else False,
        domain=_cookie_domain(),
        path="/",
        expires=refresh_exp,
    )


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
async def logout() -> Response:
    resp = Response(content={"detail": "로그아웃되었습니다."}, status_code=status.HTTP_200_OK)
    resp.delete_cookie(key="refresh_token", domain=_cookie_domain(), path="/")
    return resp


@auth_router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    request: SignUpRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    await auth_service.signup(request)
    return Response(content={"detail": "회원가입이 성공적으로 완료되었습니다."}, status_code=status.HTTP_201_CREATED)


@auth_router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    user = await auth_service.authenticate(request)
    tokens = await auth_service.login(user, role=request.role)
    return _build_login_response(tokens, login_role=request.role)


@auth_router.post("/admin/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def admin_login(
    request: LoginRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    """관리자 전용 로그인"""
    user = await auth_service.authenticate(request)
    tokens = await auth_service.login(user, role=LoginRole.ADMIN)
    return _build_login_response(tokens, login_role=LoginRole.ADMIN)


@auth_router.post("/admin/signup", status_code=status.HTTP_201_CREATED)
async def admin_signup(
    request: SignUpRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    """관리자 회원가입"""
    admin_request = request.model_copy(update={"role": LoginRole.ADMIN.value})
    await auth_service.signup(admin_request)
    return Response(content={"detail": "관리자 계정이 성공적으로 생성되었습니다."}, status_code=status.HTTP_201_CREATED)


@auth_router.get("/admin/signup", response_class=HTMLResponse)
async def admin_signup_page():
    """관리자 회원가입 페이지"""
    with open("app/ui/admin_signup.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@auth_router.get(
    "/social/{provider}/login",
    response_model=SocialLoginStartResponse,
    status_code=status.HTTP_200_OK,
)
async def social_login_start(
    provider: SocialProvider,
    social_auth_service: Annotated[SocialAuthService, Depends(SocialAuthService)],
    role: Annotated[LoginRole, Query()] = LoginRole.PATIENT,
) -> SocialLoginStartResponse:
    authorize_url = social_auth_service.build_authorize_url(provider=provider, role=role)
    return SocialLoginStartResponse(provider=provider, authorize_url=authorize_url)


@auth_router.get("/social/{provider}/callback", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def social_login_callback(
    request: Request,
    provider: SocialProvider,
    code: Annotated[str, Query(min_length=1)],
    social_auth_service: Annotated[SocialAuthService, Depends(SocialAuthService)],
    auth_service: Annotated[AuthService, Depends(AuthService)],
    jwt_service: Annotated[JwtService, Depends(JwtService)],
    state: Annotated[str | None, Query()] = None,
    role: Annotated[LoginRole | None, Query()] = None,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    profile = await social_auth_service.exchange_code_and_fetch_profile(provider=provider, code=code, state=state)
    provider_user_id = profile.get("provider_user_id")
    if not provider_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider user id is missing.")

    current_user = None
    if refresh_token:
        try:
            verified_refresh = jwt_service.verify_jwt(token=refresh_token, token_type="refresh")
            current_user = await auth_service.user_repo.get_user(verified_refresh.payload["user_id"])
        except HTTPException:
            current_user = None

    user = await social_auth_service.get_or_create_user_by_social(
        provider=provider,
        provider_user_id=provider_user_id,
        email=profile.get("email"),
        name=profile.get("name") or f"{provider.value}-user",
        current_user=current_user,
    )
    selected_role = social_auth_service.resolve_role(requested_role=role, state=state)
    tokens = await auth_service.login(user, role=selected_role)

    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header:
        redirect = RedirectResponse(url="/app", status_code=status.HTTP_302_FOUND)
        _set_refresh_cookie(redirect, tokens)
        return redirect

    return _build_login_response(tokens, login_role=selected_role)


@auth_router.get("/token/refresh", response_model=TokenRefreshResponse, status_code=status.HTTP_200_OK)
async def token_refresh(
    jwt_service: Annotated[JwtService, Depends(JwtService)],
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> Response:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is missing.")
    access_token = jwt_service.refresh_jwt(refresh_token)
    return Response(
        content=TokenRefreshResponse(access_token=str(access_token)).model_dump(), status_code=status.HTTP_200_OK
    )


@auth_router.post("/find-email", response_model=FindEmailResponse, status_code=status.HTTP_200_OK)
async def find_email(
    request: FindEmailRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> FindEmailResponse:
    email = await auth_service.find_email(request.name, request.phone_number)
    return FindEmailResponse(email=email)


@auth_router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(
    request: ResetPasswordRequest,
    auth_service: Annotated[AuthService, Depends(AuthService)],
) -> Response:
    await auth_service.reset_password(request.email, request.name, request.phone_number, request.new_password)
    return Response(content={"detail": "비밀번호가 성공적으로 재설정되었습니다."}, status_code=status.HTTP_200_OK)
