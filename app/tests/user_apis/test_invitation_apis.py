from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.healthcare import Role, UserRole
from app.models.patients import Patient
from app.models.users import User


class TestInvitationApis(TestCase):
    async def test_invite_link_list_unlink_flow(self):
        patient_email = "patient.invite@naver.com"
        caregiver_email = "caregiver.invite@naver.com"

        patient_signup_data = {
            "email": patient_email,
            "password": "Password123!",
            "name": "환자초대",
            "gender": "FEMALE",
            "birth_date": "1991-03-03",
            "phone_number": "01011112222",
        }
        caregiver_signup_data = {
            "email": caregiver_email,
            "password": "Password123!",
            "name": "보호자연동",
            "gender": "MALE",
            "birth_date": "1990-04-04",
            "phone_number": "01033334444",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=patient_signup_data)
            await client.post("/api/v1/auth/signup", json=caregiver_signup_data)

            patient_user = await User.get(email=patient_email)
            caregiver_user = await User.get(email=caregiver_email)

            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            caregiver_role, _ = await Role.get_or_create(code="CAREGIVER", defaults={"name": "CAREGIVER"})

            await UserRole.get_or_create(user_id=patient_user.id, role_id=patient_role.id)
            await UserRole.get_or_create(user_id=caregiver_user.id, role_id=caregiver_role.id)

            await Patient.get_or_create(
                user_id=patient_user.id,
                defaults={"owner_user_id": patient_user.id, "display_name": "환자초대"},
            )

            patient_login_response = await client.post(
                "/api/v1/auth/login", json={"email": patient_email, "password": "Password123!"}
            )
            patient_access_token = patient_login_response.json()["access_token"]
            patient_headers = {"Authorization": f"Bearer {patient_access_token}"}

            create_invite_response = await client.post(
                "/api/v1/users/invite-code",
                json={"expires_in_minutes": 60},
                headers=patient_headers,
            )
            assert create_invite_response.status_code == status.HTTP_201_CREATED
            invite_code = create_invite_response.json()["code"]

            caregiver_login_response = await client.post(
                "/api/v1/auth/login", json={"email": caregiver_email, "password": "Password123!"}
            )
            caregiver_access_token = caregiver_login_response.json()["access_token"]
            caregiver_headers = {"Authorization": f"Bearer {caregiver_access_token}"}

            link_response = await client.post(
                "/api/v1/users/link", json={"code": invite_code}, headers=caregiver_headers
            )
            assert link_response.status_code == status.HTTP_201_CREATED
            link_id = link_response.json()["link_id"]

            links_response = await client.get("/api/v1/users/links", headers=caregiver_headers)
            assert links_response.status_code == status.HTTP_200_OK
            assert links_response.json()["role"] == "CAREGIVER"
            assert len(links_response.json()["links"]) == 1
            assert links_response.json()["links"][0]["link_id"] == link_id

            unlink_response = await client.delete(f"/api/v1/users/links/{link_id}", headers=caregiver_headers)
            assert unlink_response.status_code == status.HTTP_200_OK
            assert unlink_response.json()["status"] == "revoked"

            links_after_unlink_response = await client.get("/api/v1/users/links", headers=caregiver_headers)
            assert links_after_unlink_response.status_code == status.HTTP_200_OK
            assert links_after_unlink_response.json()["links"] == []

    async def test_caregiver_with_self_patient_row_can_create_invite_code_in_patient_mode(self):
        caregiver_email = "caregiver.with.patient.id@naver.com"
        caregiver_signup_data = {
            "email": caregiver_email,
            "password": "Password123!",
            "name": "보호자복약겸용",
            "gender": "FEMALE",
            "birth_date": "1992-05-05",
            "phone_number": "01077778888",
            "role": "CAREGIVER",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=caregiver_signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED

            caregiver_user = await User.get(email=caregiver_email)
            patient_role = await Role.get_or_none(code="PATIENT")
            if patient_role:
                await UserRole.filter(user_id=caregiver_user.id, role_id=patient_role.id).delete()

            await Patient.get_or_create(
                user_id=caregiver_user.id,
                defaults={
                    "owner_user_id": caregiver_user.id,
                    "display_name": "보호자복약겸용",
                },
            )

            caregiver_login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": caregiver_email, "password": "Password123!", "role": "CAREGIVER"},
            )
            assert caregiver_login_response.status_code == status.HTTP_200_OK
            caregiver_access_token = caregiver_login_response.json()["access_token"]
            caregiver_headers = {"Authorization": f"Bearer {caregiver_access_token}"}

            create_invite_response = await client.post(
                "/api/v1/users/invite-code",
                json={"expires_in_minutes": 60},
                headers=caregiver_headers,
            )
            assert create_invite_response.status_code == status.HTTP_201_CREATED
            assert create_invite_response.json()["code"]
