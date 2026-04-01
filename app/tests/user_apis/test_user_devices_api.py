from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.notifications import UserDevice


class TestUserDevicesApi(TestCase):
    async def test_register_user_device_and_count(self):
        signup_data = {
            "email": "device_user@gmail.com",
            "password": "Password123!",
            "name": "기기테스터",
            "gender": "FEMALE",
            "birth_date": "1994-04-04",
            "phone_number": "01087778888",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            assert login_response.status_code == status.HTTP_200_OK
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            first_response = await client.post(
                "/api/v1/users/me/devices/register",
                json={"device_id": "web-device-001", "platform": "web"},
                headers=headers,
            )
            assert first_response.status_code == status.HTTP_200_OK
            assert first_response.json()["linked_device_count"] == 1
            assert first_response.json()["last_login_at"] is not None

            duplicate_response = await client.post(
                "/api/v1/users/me/devices/register",
                json={"device_id": "web-device-001", "platform": "web"},
                headers=headers,
            )
            assert duplicate_response.status_code == status.HTTP_200_OK
            assert duplicate_response.json()["linked_device_count"] == 1
            assert duplicate_response.json()["last_login_at"] is not None

            second_device_response = await client.post(
                "/api/v1/users/me/devices/register",
                json={"device_id": "mobile-device-001", "platform": "mobile"},
                headers=headers,
            )
            assert second_device_response.status_code == status.HTTP_200_OK
            assert second_device_response.json()["linked_device_count"] == 2
            assert second_device_response.json()["last_login_at"] is not None

        device_rows = await UserDevice.all()
        assert len(device_rows) == 2
