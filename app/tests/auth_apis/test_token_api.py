from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.core import config
from app.dependencies.rate_limit import reset_rate_limit_store
from app.main import app


class TestJWTTokenRefreshAPI(TestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        reset_rate_limit_store()

    async def test_token_refresh_success_get(self):
        # 사용자 등록 및 로그인하여 리프레시 토큰 획득
        signup_data = {
            "email": "refresh@gmail.com",
            "password": "Password123!",
            "name": "리프레시테스터",
            "gender": "MALE",
            "birth_date": "1990-01-01",
            "phone_number": "01099998888",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            login_response = await client.post(
                "/api/v1/auth/login", json={"email": "refresh@gmail.com", "password": "Password123!"}
            )

            # 쿠키에서 refresh_token 추출
            set_cookie = login_response.headers.get("set-cookie")
            refresh_token = ""
            if set_cookie:
                import re

                match = re.search(r"refresh_token=([^;]+)", set_cookie)
                if match:
                    refresh_token = match.group(1)

            # 토큰 갱신 시도
            client.cookies["refresh_token"] = refresh_token
            response = await client.get("/api/v1/auth/token/refresh")
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()
        assert response.headers.get("cache-control") == "no-store"

    async def test_token_refresh_success_post(self):
        signup_data = {
            "email": "refresh_post@gmail.com",
            "password": "Password123!",
            "name": "리프레시포스트테스터",
            "gender": "MALE",
            "birth_date": "1990-01-01",
            "phone_number": "01012341234",
        }
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)
            login_response = await client.post(
                "/api/v1/auth/login", json={"email": "refresh_post@gmail.com", "password": "Password123!"}
            )
            set_cookie = login_response.headers.get("set-cookie")
            refresh_token = ""
            if set_cookie:
                import re

                match = re.search(r"refresh_token=([^;]+)", set_cookie)
                if match:
                    refresh_token = match.group(1)

            client.cookies["refresh_token"] = refresh_token
            response = await client.post("/api/v1/auth/token/refresh")

        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()
        assert response.headers.get("cache-control") == "no-store"

    async def test_token_refresh_missing_token_get(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/auth/token/refresh")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Refresh token is missing."

    async def test_token_refresh_missing_token_post(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/token/refresh")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json()["detail"] == "Refresh token is missing."

    async def test_token_refresh_rate_limited(self):
        before_max = config.AUTH_REFRESH_RATE_LIMIT_MAX_REQUESTS
        before_window = config.AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS
        config.AUTH_REFRESH_RATE_LIMIT_MAX_REQUESTS = 2
        config.AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS = 60
        reset_rate_limit_store()

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                first = await client.post("/api/v1/auth/token/refresh")
                second = await client.post("/api/v1/auth/token/refresh")
                third = await client.post("/api/v1/auth/token/refresh")
        finally:
            config.AUTH_REFRESH_RATE_LIMIT_MAX_REQUESTS = before_max
            config.AUTH_REFRESH_RATE_LIMIT_WINDOW_SECONDS = before_window
            reset_rate_limit_store()

        assert first.status_code == status.HTTP_401_UNAUTHORIZED
        assert second.status_code == status.HTTP_401_UNAUTHORIZED
        assert third.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert third.json()["detail"]["code"] == "RATE_LIMIT_EXCEEDED"
