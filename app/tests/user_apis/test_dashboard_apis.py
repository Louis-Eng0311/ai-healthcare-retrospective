from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.documents import Document, OcrJob
from app.models.patients import Patient
from app.models.users import User


class TestDashboardApis(TestCase):
    async def test_dashboard_admin_success_and_ocr_rate_calculation(self):
        admin_signup_data = {
            "email": "dashboard.admin@gmail.com",
            "password": "Password123!",
            "name": "대시보드관리자",
            "gender": "MALE",
            "birth_date": "1990-01-01",
            "phone_number": "01088889999",
            "role": "ADMIN",
        }
        patient_signup_data = {
            "email": "dashboard.patient@gmail.com",
            "password": "Password123!",
            "name": "대시보드환자",
            "gender": "FEMALE",
            "birth_date": "1992-02-02",
            "phone_number": "01099990000",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            admin_signup_response = await client.post("/api/v1/auth/signup", json=admin_signup_data)
            assert admin_signup_response.status_code == status.HTTP_201_CREATED

            patient_signup_response = await client.post("/api/v1/auth/signup", json=patient_signup_data)
            assert patient_signup_response.status_code == status.HTTP_201_CREATED

            admin_login_response = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": admin_signup_data["email"],
                    "password": admin_signup_data["password"],
                    "role": "ADMIN",
                },
            )
            assert admin_login_response.status_code == status.HTTP_200_OK
            admin_headers = {"Authorization": f"Bearer {admin_login_response.json()['access_token']}"}

            patient_user = await User.get(email=patient_signup_data["email"])
            patient = await Patient.get(user_id=patient_user.id)
            document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=patient_user.id,
                file_url="uploads/documents/dashboard-test.jpg",
                original_filename="dashboard-test.jpg",
                file_type="image",
                status="uploaded",
            )
            await OcrJob.create(document_id=document.id, patient_id=patient.id, status="success")
            await OcrJob.create(
                document_id=document.id,
                patient_id=patient.id,
                status="failed",
                error_message="텍스트 인식 실패",
            )
            await OcrJob.create(document_id=document.id, patient_id=patient.id, status="queued")

            dashboard_response = await client.get("/api/v1/dashboard?period=7", headers=admin_headers)
            assert dashboard_response.status_code == status.HTTP_200_OK

            payload = dashboard_response.json()
            assert payload["stats"]["ocr_success_rate"] == 50.0
            assert payload["ocr_analysis"]["success_count"] == 1
            assert payload["ocr_analysis"]["failure_count"] == 1
            assert payload["ocr_analysis"]["total_processed"] == 2

    async def test_dashboard_forbidden_for_non_admin_user(self):
        patient_signup_data = {
            "email": "dashboard.nonadmin@gmail.com",
            "password": "Password123!",
            "name": "일반사용자",
            "gender": "MALE",
            "birth_date": "1993-03-03",
            "phone_number": "01011113333",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            signup_response = await client.post("/api/v1/auth/signup", json=patient_signup_data)
            assert signup_response.status_code == status.HTTP_201_CREATED

            login_response = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": patient_signup_data["email"],
                    "password": patient_signup_data["password"],
                },
            )
            assert login_response.status_code == status.HTTP_200_OK
            headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

            dashboard_response = await client.get("/api/v1/dashboard?period=7", headers=headers)
            assert dashboard_response.status_code == status.HTTP_403_FORBIDDEN
