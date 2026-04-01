from datetime import date, time

from httpx import ASGITransport, AsyncClient
from starlette import status
from tortoise.contrib.test import TestCase

from app.main import app
from app.models.documents import Document, ExtractedMed, OcrJob
from app.models.healthcare import Role, UserRole
from app.models.medications import DrugInfoCache, PatientMed
from app.models.patients import Patient
from app.models.schedules import MedSchedule, MedScheduleTime
from app.models.users import User


class TestDocumentDrugsApis(TestCase):
    async def test_get_document_drugs_success(self):
        signup_data = {
            "email": "patient.docs1@gmail.com",
            "password": "Password123!",
            "name": "문서환자1",
            "gender": "FEMALE",
            "birth_date": "1993-03-03",
            "phone_number": "01070001111",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            await UserRole.get_or_create(user_id=user.id, role_id=patient_role.id)
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자1"},
            )

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=user.id,
                file_url="uploads/documents/test.jpg",
                original_filename="test.jpg",
                file_type="image",
                status="uploaded",
            )
            ocr_job = await OcrJob.create(document_id=document.id, patient_id=patient.id, status="success")
            await ExtractedMed.create(
                ocr_job_id=ocr_job.id,
                patient_id=patient.id,
                name="암로디핀정",
                dosage_text="5mg",
                frequency_text="하루 1회",
                duration_text="30일",
                confidence=0.9,
            )

            response = await client.get(f"/api/v1/documents/{document.id}/drugs", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["document_id"] == document.id
            assert data["total"] == 1
            assert data["items"][0]["name"] == "암로디핀정"
            assert data["items"][0]["dosage_text"] == "5mg"

    async def test_patch_document_drugs_confirm_success(self):
        signup_data = {
            "email": "patient.docs2@gmail.com",
            "password": "Password123!",
            "name": "문서환자2",
            "gender": "MALE",
            "birth_date": "1992-04-04",
            "phone_number": "01070002222",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            await UserRole.get_or_create(user_id=user.id, role_id=patient_role.id)
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자2"},
            )

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=user.id,
                file_url="uploads/documents/test2.jpg",
                original_filename="test2.jpg",
                file_type="image",
                status="uploaded",
            )
            ocr_job = await OcrJob.create(document_id=document.id, patient_id=patient.id, status="success")
            extracted_med = await ExtractedMed.create(
                ocr_job_id=ocr_job.id,
                patient_id=patient.id,
                name="타이레놀정",
                dosage_text="500mg",
                confidence=0.8,
            )

            patch_payload = {
                "items": [
                    {
                        "extracted_med_id": extracted_med.id,
                        "name": "타이레놀정",
                        "dosage_text": "650mg",
                        "frequency_text": "필요 시",
                        "duration_text": "7일",
                        "confidence": 0.95,
                    },
                    {
                        "name": "암로디핀정",
                        "dosage_text": "5mg",
                        "frequency_text": "하루 1회",
                        "duration_text": "30일",
                        "confidence": 0.91,
                    },
                ],
                "replace_all": False,
                "confirm": True,
                "force_confirm": True,
            }

            response = await client.patch(f"/api/v1/documents/{document.id}/drugs", json=patch_payload, headers=headers)
            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["document_id"] == document.id
            assert data["updated_count"] == 2
            assert data["confirmed"] is True
            assert data["confirmed_patient_med_count"] == 2

            await extracted_med.refresh_from_db()
            assert extracted_med.dosage_text == "650mg"
            assert extracted_med.frequency_text == "필요 시"

            active_patient_meds = await PatientMed.filter(
                patient_id=patient.id,
                source_document_id=document.id,
                is_active=True,
            )
            assert len(active_patient_meds) == 2

    async def test_get_document_drugs_keeps_existing_rows_when_backfill_has_no_raw_text(self):
        signup_data = {
            "email": "patient.docs.backfill1@gmail.com",
            "password": "Password123!",
            "name": "문서환자백필1",
            "gender": "FEMALE",
            "birth_date": "1990-08-08",
            "phone_number": "01070009991",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            await UserRole.get_or_create(user_id=user.id, role_id=patient_role.id)
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자백필1"},
            )

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=user.id,
                file_url="uploads/documents/backfill-no-raw-text.jpg",
                original_filename="backfill-no-raw-text.jpg",
                file_type="image",
                status="uploaded",
            )
            ocr_job = await OcrJob.create(document_id=document.id, patient_id=patient.id, status="success")
            await ExtractedMed.create(
                ocr_job_id=ocr_job.id,
                patient_id=patient.id,
                name="백필테스트정",
                dosage_text=None,
                frequency_text=None,
                duration_text=None,
                confidence=0.71,
            )

            response = await client.get(f"/api/v1/documents/{document.id}/drugs", headers=headers)
            assert response.status_code == status.HTTP_200_OK

            payload = response.json()
            assert payload["total"] == 1
            assert payload["items"][0]["name"] == "백필테스트정"

            persisted_count = await ExtractedMed.filter(ocr_job_id=ocr_job.id).count()
            assert persisted_count == 1

    async def test_medication_guide_resolves_missing_drug_cache_from_display_name(self):
        signup_data = {
            "email": "patient.docs5@gmail.com",
            "password": "Password123!",
            "name": "문서환자5",
            "gender": "FEMALE",
            "birth_date": "1991-07-07",
            "phone_number": "01070005555",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            await UserRole.get_or_create(user_id=user.id, role_id=patient_role.id)
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자5"},
            )

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            cache = await DrugInfoCache.create(
                mfds_item_seq="202106092",
                drug_name_display="페나셋정",
                efficacy="해열 및 진통에 사용합니다.",
                dosage_info="1회 1정, 1일 3회 복용",
                precautions="과량 복용을 피하세요.",
            )
            patient_med = await PatientMed.create(
                patient_id=patient.id,
                source_document_id=None,
                source_ocr_job_id=None,
                source_extracted_med_id=None,
                drug_info_cache_id=None,
                display_name="페나셋정",
                dosage="1정씩",
                route=None,
                notes="횟수:3회 / 기간:3일분",
                is_active=True,
            )

            response = await client.get(
                f"/api/v1/documents/medication-guide?patient_id={patient.id}",
                headers=headers,
            )
            assert response.status_code == status.HTTP_200_OK

            body = response.json()
            assert body["total"] == 1
            item = body["items"][0]
            assert item["display_name"] == "페나셋정"
            assert item["data_source"] == "ocr_mfds"
            assert "미매칭" not in item["efficacy_summary"]

            await patient_med.refresh_from_db()
            assert patient_med.drug_info_cache_id == cache.id

    async def test_soft_delete_document_deactivates_related_meds_and_schedules(self):
        signup_data = {
            "email": "patient.docs3@gmail.com",
            "password": "Password123!",
            "name": "문서환자3",
            "gender": "FEMALE",
            "birth_date": "1995-05-05",
            "phone_number": "01070003333",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient_role, _ = await Role.get_or_create(code="PATIENT", defaults={"name": "PATIENT"})
            await UserRole.get_or_create(user_id=user.id, role_id=patient_role.id)
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자3"},
            )

            login_response = await client.post(
                "/api/v1/auth/login",
                json={"email": signup_data["email"], "password": signup_data["password"]},
            )
            access_token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {access_token}"}

            document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=user.id,
                file_url="uploads/documents/test3.jpg",
                original_filename="test3.jpg",
                file_type="image",
                status="uploaded",
            )
            patient_med = await PatientMed.create(
                patient_id=patient.id,
                source_document_id=document.id,
                display_name="삭제검증약",
                dosage="1정",
                route="PO",
                notes="test",
                is_active=True,
            )
            schedule = await MedSchedule.create(
                patient_id=patient.id,
                patient_med_id=patient_med.id,
                start_date=date(2026, 3, 19),
                end_date=date(2026, 3, 25),
                status="active",
            )
            schedule_time = await MedScheduleTime.create(
                schedule_id=schedule.id,
                time_of_day=time(8, 0),
                days_of_week="MON,TUE,WED,THU,FRI,SAT,SUN",
                is_active=True,
            )

            response = await client.delete(f"/api/v1/documents/{document.id}", headers=headers)
            assert response.status_code == status.HTTP_200_OK
            assert response.json()["status"] == "deleted"

            await document.refresh_from_db()
            await patient_med.refresh_from_db()
            await schedule.refresh_from_db()
            await schedule_time.refresh_from_db()

            assert document.status == "deleted"
            assert patient_med.is_active is False
            assert schedule.status == "inactive"
            assert schedule_time.is_active is False

    async def test_schedule_status_excludes_stale_schedule_from_deleted_document_source(self):
        signup_data = {
            "email": "patient.docs4@gmail.com",
            "password": "Password123!",
            "name": "문서환자4",
            "gender": "MALE",
            "birth_date": "1994-06-06",
            "phone_number": "01070004444",
        }

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post("/api/v1/auth/signup", json=signup_data)

            user = await User.get(email=signup_data["email"])
            patient, _ = await Patient.get_or_create(
                user_id=user.id,
                defaults={"owner_user_id": user.id, "display_name": "문서환자4"},
            )

            deleted_document = await Document.create(
                patient_id=patient.id,
                uploaded_by_user_id=user.id,
                file_url="uploads/documents/test4.jpg",
                original_filename="test4.jpg",
                file_type="image",
                status="deleted",
            )
            stale_patient_med = await PatientMed.create(
                patient_id=patient.id,
                source_document_id=deleted_document.id,
                display_name="삭제문서유래약",
                dosage="1정",
                route="PO",
                notes="stale",
                is_active=True,
            )
            stale_schedule = await MedSchedule.create(
                patient_id=patient.id,
                patient_med_id=stale_patient_med.id,
                start_date=date(2026, 3, 1),
                end_date=date(2026, 3, 31),
                status="active",
            )
            await MedScheduleTime.create(
                schedule_id=stale_schedule.id,
                time_of_day=time(8, 0),
                days_of_week="MON,TUE,WED,THU,FRI,SAT,SUN",
                is_active=True,
            )

            status_response = await client.get(
                f"/api/v1/schedules/status?patient_id={patient.id}&from=2026-03-19&to=2026-03-19"
            )
            assert status_response.status_code == status.HTTP_200_OK
            body = status_response.json()
            assert body["summary"]["expected_total"] == 0
            assert len(body["days"]) == 1
            assert body["days"][0]["items"] == []
