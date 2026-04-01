from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.healthcare import Role, UserRole
from app.models.users import User
from app.services.jwt import JwtService


class TestLoginAPI(TestCase):
    async def test_login_success(self):
        # 먼저 사용자 등록
        signup_data = {
            "email": "login_test@gmail.com",
            "password": "Password123!",
            "name": "로그인테스터",
            "gender": "FEMALE",
            "birth_date": "1995-05-05",
            "phone_number": "01011112222",
        }
        login_data = {"email": "login_test@gmail.com", "password": "Password123!"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            # 로그인 시도
            response = await client.post("/api/v1/auth/login", json=login_data)
        assert response.status_code == status.HTTP_200_OK
        assert "access_token" in response.json()
        assert response.json()["login_role"] == "PATIENT"
        # 쿠키 검증 대신 응답 헤더 확인
        assert any("refresh_token" in header for header in response.headers.get_list("set-cookie"))

    async def test_login_invalid_credentials(self):
        login_data = {"email": "nonexistent@gmail.com", "password": "WrongPassword123!"}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/auth/login", json=login_data)

        # AuthService.authenticate 에서 실패 시 HTTP_400_BAD_REQUEST 발생
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    async def test_login_guardian_role_success(self):
        signup_data = {
            "email": "guardian_login_test@gmail.com",
            "password": "Password123!",
            "name": "보호자로그인테스터",
            "gender": "FEMALE",
            "birth_date": "1997-07-07",
            "phone_number": "01033334444",
        }
        login_data = {
            "email": "guardian_login_test@gmail.com",
            "password": "Password123!",
            "role": "GUARDIAN",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED
            guardian_role, _ = await Role.get_or_create(name="GUARDIAN")
            user = await User.get(email=signup_data["email"])
            # Assign guardian role to the created user for role-based login test.
            await UserRole.get_or_create(user=user, role=guardian_role)
            response = await client.post("/api/v1/auth/login", json=login_data)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["login_role"] == "GUARDIAN"
        verified = JwtService().verify_jwt(response.json()["access_token"], token_type="access")
        assert verified.payload["login_role"] == "GUARDIAN"

    async def test_login_role_not_assigned(self):
        signup_data = {
            "email": "role_missing_test@gmail.com",
            "password": "Password123!",
            "name": "역할없음테스터",
            "gender": "MALE",
            "birth_date": "1998-08-08",
            "phone_number": "01044445555",
        }
        login_data = {
            "email": "role_missing_test@gmail.com",
            "password": "Password123!",
            "role": "GUARDIAN",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)
            response = await client.post("/api/v1/auth/login", json=login_data)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_admin_login_success(self):
        signup_data = {
            "email": "admin_login_test@gmail.com",
            "password": "Password123!",
            "name": "관리자로그인테스터",
            "gender": "MALE",
            "birth_date": "1991-01-01",
            "phone_number": "01055556666",
            "role": "ADMIN",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED

            response = await client.post(
                "/api/v1/auth/admin/login",
                json={
                    "email": signup_data["email"],
                    "password": signup_data["password"],
                },
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["login_role"] == "ADMIN"
        verified = JwtService().verify_jwt(response.json()["access_token"], token_type="access")
        assert verified.payload["login_role"] == "ADMIN"

    async def test_admin_login_forbidden_for_non_admin(self):
        signup_data = {
            "email": "non_admin_login_test@gmail.com",
            "password": "Password123!",
            "name": "일반사용자",
            "gender": "FEMALE",
            "birth_date": "1991-02-02",
            "phone_number": "01066667777",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED

            response = await client.post(
                "/api/v1/auth/admin/login",
                json={
                    "email": signup_data["email"],
                    "password": signup_data["password"],
                },
            )

        assert response.status_code == status.HTTP_403_FORBIDDEN
