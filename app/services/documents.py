import asyncio
import hashlib
import logging
import mimetypes
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image
from starlette import status
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.documents import (
    BarcodeDecodeItemResponse,
    BarcodeDecodeResponse,
    DocumentDeleteResponse,
    DocumentDrugPatchItemRequest,
    DocumentDrugPatchRequest,
    DocumentDrugPatchResponse,
    DocumentDrugsResponse,
    DocumentListItemResponse,
    DocumentListQuery,
    DocumentListResponse,
    DocumentOcrStatusResponse,
    DocumentOcrTextResponse,
    DocumentRenameRequest,
    DocumentRenameResponse,
    DocumentUploadResponse,
    ExtractedDrugItemResponse,
    ExtractedDrugMfdsInfoResponse,
    ExtractedDrugValidationResponse,
    MedicationGuideItemResponse,
    MedicationGuideResponse,
)
from app.models.documents import Document, ExtractedMed, OcrJob, OcrRawText
from app.models.dur import DurAlert
from app.models.medications import DrugInfoCache, PatientMed
from app.models.patients import CaregiverPatientLink, Patient
from app.models.schedules import MedSchedule, MedScheduleTime
from app.models.users import User
from app.services.barcode import BarcodeService
from app.services.mfds import MfdsService
from app.services.ocr import OcrService
from app.services.role_utils import user_has_role

ALLOWED_FILE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".heif"}
HEIC_FILE_EXTENSIONS = {".heic", ".heif"}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024
DRUG_FORM_SUFFIXES = ("장용캡슐", "연질캡슐", "서방정", "캡슐", "정", "액", "주", "겔", "시럽", "크림", "로션")
DOCUMENT_MED_TIME_SLOTS: tuple[tuple[str, time], ...] = (
    ("아침", time(hour=8, minute=0)),
    ("점심", time(hour=13, minute=0)),
    ("저녁", time(hour=19, minute=0)),
    ("취침", time(hour=22, minute=0)),
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DrugCacheResolution:
    cache: DrugInfoCache | None
    name_match_status: str


@dataclass(frozen=True)
class DocumentFileInfo:
    file_path: Path
    media_type: str
    download_name: str


class DocumentService:
    def __init__(self):
        self.upload_root = Path(__file__).resolve().parents[2] / "uploads" / "documents"
        self.upload_root.mkdir(parents=True, exist_ok=True)
        self.ocr_service = OcrService()
        self.mfds_service = MfdsService()
        self.barcode_service = BarcodeService()

    # 대상 patient 귀속 + 업로드/OCR 상태 생성 - REQ-USER-008, REQ-DOC-003
    async def upload_document(
        self, user: User, file: UploadFile, patient_id: int | None, title: str | None = None
    ) -> DocumentUploadResponse:
        target_patient = await self._resolve_target_patient_for_upload(user=user, patient_id=patient_id)

        original_filename = Path(file.filename or "").name
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_FILE_EXTENSIONS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")
        if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

        stored_extension = extension
        # HEIC/HEIF 파일은 OCR 호환을 위해 JPEG로 변환 - REQ-DOC-003
        if extension in HEIC_FILE_EXTENSIONS:
            file_bytes, stored_extension = self._convert_heic_to_jpeg(file_bytes=file_bytes)

        checksum = hashlib.sha256(file_bytes).hexdigest()
        stored_name = f"{datetime.now(config.TIMEZONE).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex}{stored_extension}"
        stored_path = self.upload_root / stored_name
        stored_path.write_bytes(file_bytes)
        file_url = f"uploads/documents/{stored_name}"
        normalized_title = title.strip() if title else ""
        display_filename = normalized_title or original_filename or None

        async with in_transaction() as conn:
            document = await Document.create(
                patient_id=target_patient.id,
                uploaded_by_user_id=user.id,
                file_url=file_url,
                original_filename=display_filename,
                file_type=self._normalize_file_type(stored_extension),
                file_size=len(file_bytes),
                checksum=checksum,
                status="uploaded",
                using_db=conn,
            )
            ocr_job = await OcrJob.create(
                document_id=document.id,
                patient_id=target_patient.id,
                status="queued",
                using_db=conn,
            )

        # REQ-DOC-003 - 업로드 직후 OCR 비동기 처리 시작
        asyncio.create_task(self.ocr_service.process_ocr_job(ocr_job_id=ocr_job.id))

        return DocumentUploadResponse(
            document_id=document.id,
            patient_id=document.patient_id,
            uploaded_by_user_id=document.uploaded_by_user_id,
            status=document.status,
            created_at=document.created_at,
        )

    # 문서 목록 조회 및 필터 - REQ-DOC-002
    async def list_documents(self, user: User, query: DocumentListQuery) -> DocumentListResponse:
        accessible_patient_ids = await self._resolve_accessible_patient_ids(
            user=user, requested_patient_id=query.patient_id
        )
        if not accessible_patient_ids:
            return DocumentListResponse(items=[], total=0)

        filters: dict[str, object] = {"patient_id__in": accessible_patient_ids}

        # 삭제 문서는 목록에서 제외
        if query.document_status is None:
            filters["status"] = "uploaded"
        elif query.document_status == "deleted":
            return DocumentListResponse(items=[], total=0)
        else:
            filters["status"] = query.document_status

        if query.date_from:
            filters["created_at__gte"] = datetime.combine(query.date_from, time.min, tzinfo=config.TIMEZONE)
        if query.date_to:
            filters["created_at__lt"] = datetime.combine(
                query.date_to + timedelta(days=1), time.min, tzinfo=config.TIMEZONE
            )

        documents = (
            await Document.filter(**filters)
            .select_related("patient", "uploaded_by_user")
            .prefetch_related("ocr_jobs")
            .order_by("-created_at")
        )

        confirmed_document_ids: set[int] = set()
        document_ids = [document.id for document in documents]
        if document_ids:
            confirmed_source_document_ids = await PatientMed.filter(
                source_document_id__in=document_ids,
                is_active=True,
                confirmed_at__not_isnull=True,
            ).values_list("source_document_id", flat=True)
            confirmed_document_ids = set(confirmed_source_document_ids)

        items: list[DocumentListItemResponse] = []
        for document in documents:
            latest_ocr_status = self._get_latest_ocr_status(document=document)
            if query.ocr_status and latest_ocr_status != query.ocr_status:
                continue

            items.append(
                DocumentListItemResponse(
                    document_id=document.id,
                    patient_id=document.patient_id,
                    uploaded_by_user_id=document.uploaded_by_user_id,
                    original_filename=document.original_filename,
                    file_type=document.file_type,
                    file_size=document.file_size,
                    status=document.status,
                    ocr_status=latest_ocr_status,
                    has_confirmed_meds=document.id in confirmed_document_ids,
                    created_at=document.created_at,
                )
            )

        return DocumentListResponse(items=items, total=len(items))

    # 문서 soft delete(권한 검증 포함) - REQ-DOC-001
    async def soft_delete_document(self, user: User, document_id: int) -> DocumentDeleteResponse:
        document = await Document.filter(id=document_id, status="uploaded").select_related("patient").first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        now = datetime.now(config.TIMEZONE)

        async with in_transaction() as conn:
            active_patient_med_ids = await (
                PatientMed.filter(
                    patient_id=document.patient_id,
                    source_document_id=document.id,
                    is_active=True,
                )
                .using_db(conn)
                .values_list("id", flat=True)
            )

            if active_patient_med_ids:
                active_schedule_ids = await (
                    MedSchedule.filter(
                        patient_med_id__in=list(active_patient_med_ids),
                        status="active",
                    )
                    .using_db(conn)
                    .values_list("id", flat=True)
                )

                if active_schedule_ids:
                    await MedSchedule.filter(id__in=list(active_schedule_ids)).using_db(conn).update(status="inactive")
                    await (
                        MedScheduleTime.filter(schedule_id__in=list(active_schedule_ids))
                        .using_db(conn)
                        .update(is_active=False)
                    )

                await PatientMed.filter(id__in=list(active_patient_med_ids)).using_db(conn).update(is_active=False)

            await Document.filter(id=document.id).using_db(conn).update(status="deleted", deleted_at=now)

        return DocumentDeleteResponse(
            document_id=document.id,
            status="deleted",
            deleted_at=now,
        )

    # 문서명 변경(권한 검증 포함) - REQ-DOC-002
    async def rename_document(
        self, user: User, document_id: int, payload: DocumentRenameRequest
    ) -> DocumentRenameResponse:
        document = await Document.filter(id=document_id, status="uploaded").first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        normalized_title = payload.title.strip()
        if not normalized_title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

        await Document.filter(id=document_id).update(original_filename=normalized_title)
        return DocumentRenameResponse(document_id=document.id, original_filename=normalized_title)

    async def get_document_file(self, user: User, document_id: int) -> DocumentFileInfo:
        document = await Document.filter(id=document_id, status="uploaded").first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        file_path = self._resolve_document_file_path(file_url=document.file_url)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        return DocumentFileInfo(
            file_path=file_path,
            media_type=self._resolve_media_type(file_path=file_path),
            download_name=self._resolve_download_name(
                original_filename=document.original_filename, file_path=file_path
            ),
        )

    async def decode_barcodes(self, user: User, file: UploadFile) -> BarcodeDecodeResponse:
        _ = user
        original_filename = Path(file.filename or "").name
        extension = Path(original_filename).suffix.lower() or ".png"
        if extension not in ALLOWED_FILE_EXTENSIONS and extension not in {".bmp", ".webp"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")
        if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")

        temp_dir = self.upload_root / "_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"barcode_{uuid.uuid4().hex}{extension}"
        temp_path.write_bytes(file_bytes)
        try:
            detections = await asyncio.to_thread(self.barcode_service.extract_from_file, temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        items = [
            BarcodeDecodeItemResponse(
                barcode_type=detection.barcode_type,
                barcode_value=detection.barcode_value,
            )
            for detection in detections
        ]
        return BarcodeDecodeResponse(total=len(items), items=items)

    # OCR 처리 상태 조회(권한 검증 포함) - REQ-DOC-003
    async def get_document_ocr_status(self, user: User, document_id: int) -> DocumentOcrStatusResponse:
        document = await Document.filter(id=document_id).prefetch_related("ocr_jobs").first()
        if not document or document.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        latest_job = self._get_latest_ocr_job(document=document)
        has_confirmed_meds = await self._has_active_confirmed_patient_meds(
            document_id=document.id,
            patient_id=document.patient_id,
        )
        preferred_job = await self._resolve_preferred_ocr_job_for_view(document=document, latest_job=latest_job)
        barcode_values = await self._load_barcode_values(ocr_job_id=preferred_job.id if preferred_job else None)

        return DocumentOcrStatusResponse(
            document_id=document.id,
            patient_id=document.patient_id,
            document_status=document.status,
            has_confirmed_meds=has_confirmed_meds,
            ocr_job_id=preferred_job.id if preferred_job else None,
            ocr_status=preferred_job.status if preferred_job else None,
            retry_count=preferred_job.retry_count if preferred_job else None,
            error_code=preferred_job.error_code if preferred_job else None,
            error_message=preferred_job.error_message if preferred_job else None,
            barcode_detected=bool(barcode_values),
            barcode_count=len(barcode_values),
            barcode_values=barcode_values,
            created_at=preferred_job.created_at if preferred_job else document.created_at,
            updated_at=preferred_job.updated_at if preferred_job else None,
        )

    # OCR 결과 원문 조회(권한 검증 포함) - REQ-DOC-003
    async def get_document_ocr_text(self, user: User, document_id: int) -> DocumentOcrTextResponse:
        document = await Document.filter(id=document_id).prefetch_related("ocr_jobs").first()
        if not document or document.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        latest_job = self._get_latest_ocr_job(document=document)
        preferred_job = await self._resolve_preferred_ocr_job_for_view(document=document, latest_job=latest_job)
        if not preferred_job:
            return DocumentOcrTextResponse(
                document_id=document.id,
                patient_id=document.patient_id,
                ocr_job_id=None,
                ocr_status=None,
                raw_text=None,
                created_at=document.created_at,
            )

        raw_text_row = await OcrRawText.get_or_none(ocr_job_id=preferred_job.id)
        return DocumentOcrTextResponse(
            document_id=document.id,
            patient_id=document.patient_id,
            ocr_job_id=preferred_job.id,
            ocr_status=preferred_job.status,
            raw_text=raw_text_row.raw_text if raw_text_row else None,
            created_at=raw_text_row.created_at if raw_text_row else preferred_job.created_at,
        )

    # 추출 약 목록 조회(권한 검증 포함) - REQ-DOC-006
    async def get_document_drugs(
        self, user: User, document_id: int, include_mfds: bool = True
    ) -> DocumentDrugsResponse:
        document = await Document.get_or_none(id=document_id)
        if not document or document.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        latest_success_job = await self._get_latest_success_ocr_job(document_id=document.id)
        if not latest_success_job:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UNPROCESSABLE")
        barcode_values = await self._load_barcode_values(ocr_job_id=latest_success_job.id)

        extracted_meds = await ExtractedMed.filter(ocr_job_id=latest_success_job.id).order_by("id")
        if not extracted_meds:
            # REQ-DOC-005, REQ-DOC-006 - 과거 OCR 성공건의 raw_text 기반 추출 결과 백필
            backfilled_count = await self.ocr_service.backfill_extracted_meds(ocr_job_id=latest_success_job.id)
            if backfilled_count > 0:
                extracted_meds = await ExtractedMed.filter(ocr_job_id=latest_success_job.id).order_by("id")
        elif self._needs_extracted_meds_backfill(extracted_meds=extracted_meds):
            # REQ-DOC-005, REQ-DOC-006 - 구버전 파서 결과(용량/횟수/기간 비어있는 경우) 자동 보정
            backfilled_count = await self.ocr_service.backfill_extracted_meds(ocr_job_id=latest_success_job.id)
            if backfilled_count > 0:
                extracted_meds = await ExtractedMed.filter(ocr_job_id=latest_success_job.id).order_by("id")

        if not extracted_meds:
            restored_count = await self._restore_extracted_meds_from_confirmed_patient_meds(
                document=document,
                ocr_job=latest_success_job,
            )
            if restored_count > 0:
                extracted_meds = await ExtractedMed.filter(ocr_job_id=latest_success_job.id).order_by("id")

        response_items = await self._build_extracted_drug_items(
            extracted_meds=extracted_meds, fetch_missing=include_mfds
        )

        return DocumentDrugsResponse(
            document_id=document.id,
            patient_id=document.patient_id,
            ocr_job_id=latest_success_job.id,
            ocr_status=latest_success_job.status,
            barcode_detected=bool(barcode_values),
            barcode_count=len(barcode_values),
            barcode_values=barcode_values,
            items=response_items,
            total=len(response_items),
        )

    # 추출 약 수정/확정(권한 검증 포함) - REQ-DOC-007
    async def patch_document_drugs(
        self, user: User, document_id: int, payload: DocumentDrugPatchRequest
    ) -> DocumentDrugPatchResponse:
        document = await Document.get_or_none(id=document_id)
        if not document or document.status == "deleted":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        latest_success_job = await self._get_latest_success_ocr_job(document_id=document.id)
        if not latest_success_job:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UNPROCESSABLE")

        updated_meds = await self._apply_extracted_med_patch(
            ocr_job_id=latest_success_job.id,
            patient_id=document.patient_id,
            payload=payload,
        )
        confirmed_patient_med_count = await self._confirm_document_drugs_if_needed(
            document=document,
            ocr_job=latest_success_job,
            extracted_meds=updated_meds,
            confirm=payload.confirm,
            force_confirm=payload.force_confirm,
        )

        response_items = await self._build_extracted_drug_items(extracted_meds=updated_meds, fetch_missing=True)
        return DocumentDrugPatchResponse(
            document_id=document.id,
            patient_id=document.patient_id,
            ocr_job_id=latest_success_job.id,
            confirmed=payload.confirm,
            updated_count=len(response_items),
            confirmed_patient_med_count=confirmed_patient_med_count,
            items=response_items,
        )

    # 추출 약 수정 내용 DB 반영(replace_all 포함) - REQ-DOC-007
    async def _apply_extracted_med_patch(
        self, ocr_job_id: int, patient_id: int, payload: DocumentDrugPatchRequest
    ) -> list[ExtractedMed]:
        async with in_transaction() as conn:
            existing_meds = await ExtractedMed.filter(ocr_job_id=ocr_job_id).using_db(conn)
            existing_by_id = {med.id: med for med in existing_meds}
            touched_med_ids: list[int] = []

            for item in payload.items:
                if item.extracted_med_id is not None:
                    target_med = existing_by_id.get(item.extracted_med_id)
                    if not target_med:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

                    await (
                        ExtractedMed.filter(id=target_med.id)
                        .using_db(conn)
                        .update(
                            name=item.name.strip(),
                            dosage_text=self._nullable_str(item.dosage_text),
                            frequency_text=self._normalize_frequency_text_for_storage(item.frequency_text),
                            duration_text=self._nullable_str(item.duration_text),
                            confidence=item.confidence,
                        )
                    )
                    touched_med_ids.append(target_med.id)
                    continue

                created_med = await self._create_extracted_med_from_patch_item(
                    item=item,
                    ocr_job_id=ocr_job_id,
                    patient_id=patient_id,
                    using_db=conn,
                )
                touched_med_ids.append(created_med.id)

            if payload.replace_all:
                delete_query = ExtractedMed.filter(ocr_job_id=ocr_job_id).using_db(conn)
                if touched_med_ids:
                    delete_query = delete_query.exclude(id__in=touched_med_ids)
                await delete_query.delete()

        return await ExtractedMed.filter(ocr_job_id=ocr_job_id).order_by("id")

    # 추출 약 확정 저장(검수 가드 + patient_meds 동기화) - REQ-DOC-007, REQ-DRUG-001, REQ-DRUG-005
    async def _confirm_document_drugs_if_needed(
        self,
        document: Document,
        ocr_job: OcrJob,
        extracted_meds: list[ExtractedMed],
        confirm: bool,
        force_confirm: bool,
    ) -> int:
        if not confirm:
            return 0

        if not force_confirm:
            review_required_meds = await self._collect_review_required_med_names(extracted_meds=extracted_meds)
            if review_required_meds:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "code": "UNPROCESSABLE",
                        "message": "REVIEW_REQUIRED_BEFORE_CONFIRM",
                        "review_required_meds": review_required_meds,
                    },
                )

        async with in_transaction() as conn:
            return await self._sync_confirmed_meds(
                document=document,
                ocr_job=ocr_job,
                extracted_meds=extracted_meds,
                using_db=conn,
            )

    # 복약안내 카드 조회(문서별/전체 + 기존 복용약 포함 옵션) - REQ-DOC-007, REQ-DRUG-002, REQ-DRUG-003
    async def get_medication_guide(
        self,
        user: User,
        patient_id: int,
        document_id: int | None = None,
        include_other_active: bool = False,
    ) -> MedicationGuideResponse:
        target_patient = await Patient.get_or_none(id=patient_id)
        if not target_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        patient_meds = await self._load_patient_meds_for_guide(
            patient_id=patient_id,
            document_id=document_id,
            include_other_active=include_other_active,
        )
        extracted_med_map = await self._build_extracted_med_map(patient_meds=patient_meds)
        extracted_med_fallback_map = await self._build_extracted_med_fallback_map(patient_meds=patient_meds)
        source_document_map = await self._build_source_document_map(patient_meds=patient_meds)

        interaction_map = await self._build_patient_med_interaction_map(patient_meds=patient_meds)
        response_items: list[MedicationGuideItemResponse] = []
        for patient_med in patient_meds:
            extracted_med = (
                extracted_med_map.get(patient_med.source_extracted_med_id)
                if patient_med.source_extracted_med_id
                else None
            )
            if extracted_med is None:
                extracted_med = self._find_extracted_med_fallback(
                    patient_med=patient_med,
                    extracted_med_fallback_map=extracted_med_fallback_map,
                )
            drug_info_cache = await self._ensure_patient_med_drug_cache_for_guide(patient_med=patient_med)
            data_source = "ocr_mfds" if drug_info_cache else "ocr_only"
            source_document = (
                source_document_map.get(patient_med.source_document_id) if patient_med.source_document_id else None
            )

            # 복약방법은 MFDS 우선, 미매칭이면 OCR 구조화 데이터 기반으로 fallback - REQ-DOC-007, REQ-DRUG-002
            dosage_instructions = self._split_guide_text_to_bullets(
                text=(drug_info_cache.dosage_info if drug_info_cache else None),
                fallback_text=self._build_ocr_fallback_instructions_text(
                    patient_med=patient_med,
                    extracted_med=extracted_med,
                ),
            )
            if not dosage_instructions:
                dosage_instructions = ["처방전 또는 의사/약사 안내에 따라 복용하세요."]

            # 주의사항은 MFDS 우선, 미매칭이면 안전 기본 수칙 fallback - REQ-DOC-007, REQ-DRUG-002
            precautions = self._split_guide_text_to_bullets(
                text=(drug_info_cache.precautions if drug_info_cache else None),
                fallback_text=self._build_ocr_fallback_precautions_text(extracted_med=extracted_med),
            )
            if not precautions:
                precautions = self._build_default_precautions()

            prescribed_days = self._extract_prescribed_days(patient_med=patient_med, extracted_med=extracted_med)
            prescribed_at = self._resolve_prescribed_at_date(patient_med=patient_med, source_document=source_document)
            expected_end_date = self._calculate_expected_end_date(
                prescribed_at=prescribed_at,
                prescribed_days=prescribed_days,
            )

            response_items.append(
                MedicationGuideItemResponse(
                    patient_med_id=patient_med.id,
                    patient_id=patient_med.patient_id,
                    display_name=patient_med.display_name,
                    dosage=patient_med.dosage or (extracted_med.dosage_text if extracted_med else None),
                    frequency_text=self._coalesce_frequency_text(patient_med=patient_med, extracted_med=extracted_med),
                    data_source=data_source,
                    efficacy_summary=self._build_efficacy_summary(
                        display_name=patient_med.display_name,
                        drug_info_cache=drug_info_cache,
                    ),
                    dosage_instructions=dosage_instructions,
                    precautions=precautions,
                    storage_method=self._build_storage_method(drug_info_cache=drug_info_cache),
                    prescribed_days=prescribed_days,
                    prescribed_at=prescribed_at,
                    expected_end_date=expected_end_date,
                    interaction_warnings=interaction_map.get(patient_med.id, []),
                    source_document_id=patient_med.source_document_id,
                    confirmed_at=patient_med.confirmed_at,
                )
            )

        return MedicationGuideResponse(
            patient_id=patient_id,
            document_id=document_id,
            include_other_active=include_other_active,
            total=len(response_items),
            items=response_items,
        )

    # 복약안내 대상 patient_meds 로드 - REQ-DOC-007
    async def _load_patient_meds_for_guide(
        self, patient_id: int, document_id: int | None, include_other_active: bool
    ) -> list[PatientMed]:
        if document_id is not None:
            source_document = await Document.filter(id=document_id, status="uploaded").first()
            if not source_document or source_document.patient_id != patient_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        patient_med_query = PatientMed.filter(patient_id=patient_id, is_active=True)
        if document_id is not None and not include_other_active:
            patient_med_query = patient_med_query.filter(source_document_id=document_id)

        return await patient_med_query.select_related("drug_info_cache").order_by("-confirmed_at", "-updated_at")

    # 복약안내 조회 시 미매칭 patient_med의 drug_info_cache를 1회 보정
    async def _ensure_patient_med_drug_cache_for_guide(self, patient_med: PatientMed) -> DrugInfoCache | None:
        if patient_med.drug_info_cache:
            return patient_med.drug_info_cache

        cache_resolution = await self._resolve_drug_cache(name=patient_med.display_name, fetch_missing=True)
        matched_cache = cache_resolution.cache
        if not matched_cache:
            return None

        await PatientMed.filter(id=patient_med.id).update(drug_info_cache_id=matched_cache.id)
        patient_med.drug_info_cache_id = matched_cache.id
        patient_med.drug_info_cache = matched_cache
        return matched_cache

    # 복약안내용 ExtractedMed 맵 구성 - REQ-DOC-007
    @staticmethod
    async def _build_extracted_med_map(patient_meds: list[PatientMed]) -> dict[int, ExtractedMed]:
        extracted_med_id_list = [med.source_extracted_med_id for med in patient_meds if med.source_extracted_med_id]
        if not extracted_med_id_list:
            return {}
        extracted_meds = await ExtractedMed.filter(id__in=extracted_med_id_list)
        return {med.id: med for med in extracted_meds}

    # 복약안내용 ExtractedMed fallback 맵 구성(ocr_job_id + 약명) - REQ-DOC-007
    async def _build_extracted_med_fallback_map(
        self, patient_meds: list[PatientMed]
    ) -> dict[tuple[int, str], ExtractedMed]:
        source_ocr_job_ids = [med.source_ocr_job_id for med in patient_meds if med.source_ocr_job_id]
        if not source_ocr_job_ids:
            return {}

        extracted_meds = await ExtractedMed.filter(ocr_job_id__in=source_ocr_job_ids)
        fallback_map: dict[tuple[int, str], ExtractedMed] = {}
        for extracted_med in extracted_meds:
            normalized_name = self._normalize_mfds_keyword(value=extracted_med.name)
            if not normalized_name:
                continue
            fallback_key = (extracted_med.ocr_job_id, normalized_name)
            if fallback_key not in fallback_map:
                fallback_map[fallback_key] = extracted_med
        return fallback_map

    # source_extracted_med_id 불일치 시 fallback 추출약 조회 - REQ-DOC-007
    def _find_extracted_med_fallback(
        self, patient_med: PatientMed, extracted_med_fallback_map: dict[tuple[int, str], ExtractedMed]
    ) -> ExtractedMed | None:
        if not patient_med.source_ocr_job_id:
            return None
        normalized_name = self._normalize_mfds_keyword(value=patient_med.display_name)
        if not normalized_name:
            return None
        fallback_key = (patient_med.source_ocr_job_id, normalized_name)
        return extracted_med_fallback_map.get(fallback_key)

    async def _restore_extracted_meds_from_confirmed_patient_meds(self, *, document: Document, ocr_job: OcrJob) -> int:
        confirmed_patient_meds = await PatientMed.filter(
            patient_id=document.patient_id,
            source_document_id=document.id,
            is_active=True,
        ).order_by("-confirmed_at", "-updated_at", "id")
        if not confirmed_patient_meds:
            return 0

        created_count = 0
        for patient_med in confirmed_patient_meds:
            med_name = self._nullable_str(patient_med.display_name)
            if not med_name:
                continue

            notes_text = str(patient_med.notes or "")
            dosage_from_notes = self._extract_confirmed_med_note_value(notes=notes_text, key="용량")
            frequency_from_notes = self._extract_confirmed_med_note_value(notes=notes_text, key="횟수")
            duration_from_notes = self._extract_confirmed_med_note_value(notes=notes_text, key="기간")

            await ExtractedMed.create(
                ocr_job_id=ocr_job.id,
                patient_id=document.patient_id,
                name=med_name,
                dosage_text=self._nullable_str(patient_med.dosage) or dosage_from_notes,
                frequency_text=self._normalize_frequency_text_for_storage(frequency_from_notes),
                duration_text=duration_from_notes,
                confidence=None,
            )
            created_count += 1

        if created_count > 0:
            logger.info(
                "Restored extracted meds from confirmed patient meds (document_id=%s, ocr_job_id=%s, count=%s)",
                document.id,
                ocr_job.id,
                created_count,
            )
        return created_count

    # 복약안내용 source document 맵 구성 - REQ-DOC-007
    @staticmethod
    async def _build_source_document_map(patient_meds: list[PatientMed]) -> dict[int, Document]:
        source_document_ids = [med.source_document_id for med in patient_meds if med.source_document_id]
        if not source_document_ids:
            return {}
        source_documents = await Document.filter(id__in=source_document_ids)
        return {document.id: document for document in source_documents}

    # 대상 PATIENT 귀속 검증 - REQ-USER-008, REQ-DOC-003
    async def _resolve_target_patient_for_upload(self, user: User, patient_id: int | None) -> Patient:
        is_caregiver = await user_has_role(user.id, "CAREGIVER", "GUARDIAN")

        own_patient = await Patient.get_or_none(user_id=user.id)

        if patient_id is None:
            if own_patient:
                return own_patient
            if is_caregiver:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        target_patient = await Patient.get_or_none(id=patient_id)
        if not target_patient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if own_patient and own_patient.id == patient_id:
            return target_patient

        if is_caregiver and await self._is_active_link(caregiver_user_id=user.id, patient_id=patient_id):
            return target_patient

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

    # 문서 조회 대상 환자 범위 계산 - REQ-DOC-002
    async def _resolve_accessible_patient_ids(self, user: User, requested_patient_id: int | None) -> list[int]:
        is_caregiver = await user_has_role(user.id, "CAREGIVER", "GUARDIAN")

        own_patient = await Patient.get_or_none(user_id=user.id)
        own_patient_id = own_patient.id if own_patient else None

        linked_patient_ids: list[int] = []
        if is_caregiver:
            links = await CaregiverPatientLink.filter(
                caregiver_user_id=user.id,
                status="active",
                revoked_at__isnull=True,
            ).values_list("patient_id", flat=True)
            linked_patient_ids = list(links)

        if requested_patient_id is not None:
            if own_patient_id and requested_patient_id == own_patient_id:
                return [requested_patient_id]
            if requested_patient_id in linked_patient_ids:
                return [requested_patient_id]
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        accessible = set(linked_patient_ids)
        if own_patient_id:
            accessible.add(own_patient_id)
        return sorted(accessible)

    # 문서 접근 권한 확인 - REQ-DOC-001, REQ-DOC-002
    async def _has_patient_access(self, user: User, patient_id: int) -> bool:
        own_patient = await Patient.get_or_none(user_id=user.id)
        if own_patient and own_patient.id == patient_id:
            return True
        return await self._is_active_link(caregiver_user_id=user.id, patient_id=patient_id)

    # 보호자-환자 활성 연동 확인 - REQ-USER-008, REQ-DOC-001, REQ-DOC-002
    async def _is_active_link(self, caregiver_user_id: int, patient_id: int) -> bool:
        return await CaregiverPatientLink.filter(
            caregiver_user_id=caregiver_user_id,
            patient_id=patient_id,
            status="active",
            revoked_at__isnull=True,
        ).exists()

    # 업로드 파일 타입 정규화 - REQ-DOC-003
    @staticmethod
    def _normalize_file_type(extension: str) -> str:
        return "pdf" if extension == ".pdf" else "image"

    def _resolve_document_file_path(self, file_url: str) -> Path:
        relative_path = Path(file_url)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        file_path = (Path(__file__).resolve().parents[2] / relative_path).resolve()
        upload_root = self.upload_root.resolve()
        if upload_root not in file_path.parents:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")
        return file_path

    @staticmethod
    def _resolve_media_type(file_path: Path) -> str:
        media_type = mimetypes.guess_type(file_path.name)[0]
        if media_type:
            return media_type

        suffix = file_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        if suffix == ".pdf":
            return "application/pdf"
        return "application/octet-stream"

    @staticmethod
    def _resolve_download_name(original_filename: str | None, file_path: Path) -> str:
        if not original_filename:
            return file_path.name

        filename = original_filename.strip()
        if not filename:
            return file_path.name
        if Path(filename).suffix:
            return filename
        return f"{filename}{file_path.suffix}"

    # HEIC/HEIF -> JPEG 변환 - REQ-DOC-003
    @staticmethod
    def _convert_heic_to_jpeg(file_bytes: bytes) -> tuple[bytes, str]:
        try:
            # pillow-heif 설치 시 HEIC 오프너 자동 등록
            try:
                import pillow_heif  # type: ignore

                pillow_heif.register_heif_opener()
            except Exception:  # noqa: BLE001
                pass

            with Image.open(BytesIO(file_bytes)) as image:
                rgb_image = image.convert("RGB")
                output = BytesIO()
                rgb_image.save(output, format="JPEG", quality=95)
                converted_bytes = output.getvalue()
            if not converted_bytes:
                raise ValueError("EMPTY_CONVERTED_IMAGE")
            return converted_bytes, ".jpg"
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_INPUT") from exc

    # 문서별 최신 OCR 상태 계산 - REQ-DOC-002, REQ-DOC-003
    @staticmethod
    def _get_latest_ocr_status(document: Document) -> str | None:
        latest_job = DocumentService._get_latest_ocr_job(document=document)
        if not latest_job:
            return None
        if latest_job.status == "success":
            return "success"

        has_success_job = any(job.status == "success" for job in list(document.ocr_jobs))
        if has_success_job:
            return "success"
        return latest_job.status

    # 문서별 최신 OCR Job 계산 - REQ-DOC-003
    @staticmethod
    def _get_latest_ocr_job(document: Document) -> OcrJob | None:
        jobs = list(document.ocr_jobs)
        if not jobs:
            return None
        return max(jobs, key=lambda job: job.created_at)

    async def _get_latest_success_ocr_job(self, document_id: int) -> OcrJob | None:
        return await OcrJob.filter(document_id=document_id, status="success").order_by("-created_at").first()

    async def _has_active_confirmed_patient_meds(self, *, document_id: int, patient_id: int) -> bool:
        return await PatientMed.filter(
            patient_id=patient_id,
            source_document_id=document_id,
            is_active=True,
            confirmed_at__not_isnull=True,
        ).exists()

    async def _resolve_preferred_ocr_job_for_view(
        self, *, document: Document, latest_job: OcrJob | None
    ) -> OcrJob | None:
        if not latest_job:
            return None

        latest_success_job = await self._get_latest_success_ocr_job(document_id=document.id)
        if latest_success_job:
            return latest_success_job
        return latest_job

    # 바코드 인식 결과 로드 - REQ-DOC-009
    async def _load_barcode_values(self, ocr_job_id: int | None) -> list[str]:
        if ocr_job_id is None:
            return []
        raw_text_row = await OcrRawText.get_or_none(ocr_job_id=ocr_job_id)
        if not raw_text_row or not raw_text_row.raw_text:
            return []
        return self._extract_barcode_values(raw_text=raw_text_row.raw_text)

    # raw_text에서 바코드 값 파싱 - REQ-DOC-009
    @staticmethod
    def _extract_barcode_values(raw_text: str) -> list[str]:
        barcode_values: list[str] = []
        seen_values: set[str] = set()
        for raw_line in raw_text.splitlines():
            line = raw_line.strip()
            if not line.startswith("type="):
                continue
            matched = re.search(r"value=(.+)$", line)
            if not matched:
                continue
            barcode_value = matched.group(1).strip()
            if not barcode_value or barcode_value in seen_values:
                continue
            seen_values.add(barcode_value)
            barcode_values.append(barcode_value)
        return barcode_values

    # 기존 추출 결과가 비어있는 경우 재파싱 필요 여부 판별 - REQ-DOC-006
    @staticmethod
    def _needs_extracted_meds_backfill(extracted_meds: list[ExtractedMed]) -> bool:
        if not extracted_meds:
            return False
        empty_schedule_count = 0
        for med in extracted_meds:
            if not med.dosage_text and not med.frequency_text and not med.duration_text:
                empty_schedule_count += 1
        return empty_schedule_count >= max(1, int(len(extracted_meds) * 0.7))

    # 추출 약 응답 변환 - REQ-DOC-006, REQ-DOC-007
    @staticmethod
    def _to_extracted_drug_item_response(
        med: ExtractedMed,
        validation: ExtractedDrugValidationResponse,
        mfds_info: ExtractedDrugMfdsInfoResponse | None = None,
    ) -> ExtractedDrugItemResponse:
        return ExtractedDrugItemResponse(
            extracted_med_id=med.id,
            ocr_job_id=med.ocr_job_id,
            patient_id=med.patient_id,
            name=med.name,
            dosage_text=med.dosage_text,
            frequency_text=med.frequency_text,
            duration_text=med.duration_text,
            confidence=float(med.confidence) if med.confidence is not None else None,
            mfds_info=mfds_info,
            validation=validation,
            created_at=med.created_at,
        )

    # 추출 약 신규 생성 - REQ-DOC-007
    async def _create_extracted_med_from_patch_item(
        self,
        item: DocumentDrugPatchItemRequest,
        ocr_job_id: int,
        patient_id: int,
        using_db,
    ) -> ExtractedMed:
        return await ExtractedMed.create(
            ocr_job_id=ocr_job_id,
            patient_id=patient_id,
            name=item.name.strip(),
            dosage_text=self._nullable_str(item.dosage_text),
            frequency_text=self._normalize_frequency_text_for_storage(item.frequency_text),
            duration_text=self._nullable_str(item.duration_text),
            confidence=item.confidence,
            using_db=using_db,
        )

    # 추출 약 확정 시 patient_meds 동기화 - REQ-DOC-007
    async def _sync_confirmed_meds(
        self, document: Document, ocr_job: OcrJob, extracted_meds: list[ExtractedMed], using_db
    ) -> int:
        now = datetime.now(config.TIMEZONE)
        source_start_date = (document.created_at or now).date()

        existing_patient_meds = (
            await PatientMed.filter(
                patient_id=document.patient_id,
                source_document_id=document.id,
                is_active=True,
            )
            .using_db(using_db)
            .all()
        )
        existing_patient_med_ids = [med.id for med in existing_patient_meds]

        if existing_patient_med_ids:
            existing_schedule_ids = (
                await MedSchedule.filter(patient_med_id__in=existing_patient_med_ids, status="active")
                .using_db(using_db)
                .values_list("id", flat=True)
            )
            if existing_schedule_ids:
                await MedSchedule.filter(id__in=existing_schedule_ids).using_db(using_db).update(status="inactive")
                await (
                    MedScheduleTime.filter(schedule_id__in=list(existing_schedule_ids))
                    .using_db(using_db)
                    .update(is_active=False)
                )

        await (
            PatientMed.filter(
                patient_id=document.patient_id,
                source_document_id=document.id,
                is_active=True,
            )
            .using_db(using_db)
            .update(is_active=False)
        )

        created_count = 0
        for med in extracted_meds:
            matched_cache_resolution = await self._resolve_drug_cache(name=med.name, fetch_missing=True)
            matched_cache = matched_cache_resolution.cache
            patient_med = await PatientMed.create(
                patient_id=document.patient_id,
                source_document_id=document.id,
                source_ocr_job_id=ocr_job.id,
                source_extracted_med_id=med.id,
                drug_info_cache_id=matched_cache.id if matched_cache else None,
                display_name=med.name,
                dosage=med.dosage_text,
                route=None,
                notes=self._build_confirmed_med_note(extracted_med=med),
                is_active=True,
                confirmed_at=now,
                using_db=using_db,
            )
            await self._sync_confirmed_med_schedule(
                patient_med=patient_med,
                extracted_med=med,
                source_start_date=source_start_date,
                using_db=using_db,
            )
            created_count += 1
        return created_count

    async def _sync_confirmed_med_schedule(
        self,
        *,
        patient_med: PatientMed,
        extracted_med: ExtractedMed,
        source_start_date: date,
        using_db,
    ) -> None:
        schedule_times = self._extract_schedule_times_from_frequency_text(extracted_med.frequency_text)
        if not schedule_times:
            return

        end_date = self._extract_schedule_end_date(
            start_date=source_start_date,
            duration_text=extracted_med.duration_text,
        )
        schedule = await MedSchedule.create(
            patient_id=patient_med.patient_id,
            patient_med_id=patient_med.id,
            start_date=source_start_date,
            end_date=end_date,
            status="active",
            using_db=using_db,
        )

        for scheduled_time in schedule_times:
            await MedScheduleTime.create(
                schedule_id=schedule.id,
                time_of_day=scheduled_time,
                days_of_week=None,
                is_active=True,
                using_db=using_db,
            )

    @staticmethod
    def _extract_schedule_times_from_frequency_text(frequency_text: str | None) -> list[time]:
        if not frequency_text:
            return []

        detected_times: list[time] = []
        for keyword, slot_time in DOCUMENT_MED_TIME_SLOTS:
            if keyword in frequency_text and slot_time not in detected_times:
                detected_times.append(slot_time)

        return detected_times

    @staticmethod
    def _extract_schedule_end_date(*, start_date: date, duration_text: str | None) -> date | None:
        if not duration_text:
            return start_date

        match = re.search(r"(\d+)\s*(?:일분|일|days?)", duration_text, flags=re.IGNORECASE)
        if not match:
            return start_date

        duration_days = int(match.group(1))
        if duration_days <= 0:
            return start_date

        return start_date + timedelta(days=duration_days - 1)

    # 입력 문자열 정규화 - REQ-DOC-007
    @staticmethod
    def _nullable_str(value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed if trimmed else None

    # 추출 약 목록 응답 조립 - REQ-DOC-006, REQ-DOC-007, REQ-DRUG-001, REQ-DRUG-005
    async def _build_extracted_drug_items(
        self, extracted_meds: list[ExtractedMed], fetch_missing: bool
    ) -> list[ExtractedDrugItemResponse]:
        response_items: list[ExtractedDrugItemResponse] = []
        for med in extracted_meds:
            cache_resolution = await self._resolve_drug_cache(name=med.name, fetch_missing=fetch_missing)
            cache = cache_resolution.cache
            mfds_info = (
                ExtractedDrugMfdsInfoResponse(
                    drug_info_cache_id=cache.id,
                    mfds_item_seq=cache.mfds_item_seq,
                    drug_name_display=cache.drug_name_display,
                    manufacturer=cache.manufacturer,
                    efficacy=cache.efficacy,
                    dosage_info=cache.dosage_info,
                    precautions=cache.precautions,
                    storage_method=cache.storage_method,
                    expires_at=cache.expires_at,
                )
                if cache
                else None
            )

            validation = self._build_validation_status(med=med, cache_resolution=cache_resolution)
            response_items.append(
                self._to_extracted_drug_item_response(med=med, validation=validation, mfds_info=mfds_info)
            )
        return response_items

    # 추출 약 확정 전 검수 필요 약명 수집 - REQ-DOC-007, REQ-DRUG-001, REQ-DRUG-005
    async def _collect_review_required_med_names(self, extracted_meds: list[ExtractedMed]) -> list[str]:
        review_required_meds: list[str] = []
        seen_names: set[str] = set()
        for med in extracted_meds:
            cache_resolution = await self._resolve_drug_cache(name=med.name, fetch_missing=True)
            validation = self._build_validation_status(med=med, cache_resolution=cache_resolution)
            if not validation.needs_review:
                continue
            if med.name in seen_names:
                continue
            seen_names.add(med.name)
            review_required_meds.append(med.name)
        return review_required_meds

    # 자동 검증 상태 계산 - REQ-DRUG-001, REQ-DRUG-005
    def _build_validation_status(
        self, med: ExtractedMed, cache_resolution: DrugCacheResolution
    ) -> ExtractedDrugValidationResponse:
        dosage_check_status = self._evaluate_dosage_check_status(med=med, cache=cache_resolution.cache)
        needs_review = cache_resolution.name_match_status != "exact" or dosage_check_status in {"missing", "mismatch"}

        reason = None
        if cache_resolution.name_match_status == "unmatched":
            reason = "약명 매칭 실패"
        elif dosage_check_status == "mismatch":
            reason = "용량 정보 불일치 가능성"
        elif dosage_check_status == "missing":
            reason = "용량 정보 누락"

        return ExtractedDrugValidationResponse(
            name_match_status=cache_resolution.name_match_status,  # type: ignore[arg-type]
            dosage_check_status=dosage_check_status,  # type: ignore[arg-type]
            needs_review=needs_review,
            reason=reason,
        )

    # 용량 검증 상태 계산 - REQ-DRUG-002, REQ-DRUG-005
    def _evaluate_dosage_check_status(self, med: ExtractedMed, cache: DrugInfoCache | None) -> str:
        if not med.dosage_text:
            return "missing"
        if not cache or not cache.dosage_info:
            return "unknown"

        normalized_dosage_text = self._normalize_mfds_keyword(value=med.dosage_text)
        normalized_dosage_info = self._normalize_mfds_keyword(value=cache.dosage_info)
        if normalized_dosage_text and normalized_dosage_text in normalized_dosage_info:
            return "ok"
        return "mismatch"

    # 약명 기준 drug_info_cache 조회/동기화 - REQ-DRUG-001, REQ-DRUG-002, REQ-DRUG-003
    async def _resolve_drug_cache(self, name: str, fetch_missing: bool) -> DrugCacheResolution:
        keywords = self._build_cache_search_keywords(name=name)
        if not keywords:
            return DrugCacheResolution(cache=None, name_match_status="unmatched")

        for keyword in keywords:
            matched_cache, name_match_status = await self._find_best_drug_cache(keyword=keyword)
            if matched_cache:
                return DrugCacheResolution(cache=matched_cache, name_match_status=name_match_status)

        if not fetch_missing or not config.MFDS_SERVICE_KEY:
            return DrugCacheResolution(cache=None, name_match_status="unmatched")

        for keyword in keywords[:2]:
            try:
                await self.mfds_service.search_easy_drug_info(drug_name=keyword, num_of_rows=5)
            except HTTPException:
                continue

            matched_cache, name_match_status = await self._find_best_drug_cache(keyword=keyword)
            if matched_cache:
                return DrugCacheResolution(cache=matched_cache, name_match_status=name_match_status)

        return DrugCacheResolution(cache=None, name_match_status="unmatched")

    # 약명 기반 캐시 후보 조회(부분 일치 + 형태소 suffix 제거 fallback) - REQ-DRUG-001, REQ-DRUG-005
    async def _find_best_drug_cache(self, keyword: str) -> tuple[DrugInfoCache | None, str]:  # noqa: C901
        candidates = await DrugInfoCache.filter(drug_name_display__contains=keyword).order_by("-updated_at").limit(10)
        if not candidates:
            stripped_keyword = self._strip_drug_form_suffix(keyword=keyword)
            if stripped_keyword and stripped_keyword != keyword:
                candidates = (
                    await DrugInfoCache.filter(drug_name_display__contains=stripped_keyword)
                    .order_by("-updated_at")
                    .limit(10)
                )
                keyword = stripped_keyword
        if not candidates:
            # 부분 일치가 없으면 최근 캐시에서 fuzzy 후보 탐색 - REQ-DRUG-001, REQ-DRUG-005
            fuzzy_candidate = await self._find_fuzzy_drug_cache(keyword=keyword)
            if fuzzy_candidate:
                return fuzzy_candidate, "candidate"
            return None, "unmatched"

        normalized_keyword = self._normalize_mfds_keyword(value=keyword)

        def score(cache: DrugInfoCache) -> tuple[int, int]:
            normalized_display_name = self._normalize_mfds_keyword(value=cache.drug_name_display or "")
            if not normalized_display_name:
                return (0, 0)
            if normalized_display_name == normalized_keyword:
                return (3, len(normalized_display_name))
            if normalized_keyword in normalized_display_name:
                return (2, len(normalized_display_name))
            if normalized_display_name in normalized_keyword:
                return (1, len(normalized_display_name))
            return (0, len(normalized_display_name))

        best_cache = max(candidates, key=score)
        best_score = score(best_cache)[0]
        if best_score == 3:
            return best_cache, "exact"
        if best_score in {1, 2}:
            return best_cache, "candidate"
        return None, "unmatched"

    # MFDS 조회 키워드 정규화 - REQ-DRUG-005
    @staticmethod
    def _normalize_mfds_keyword(value: str) -> str:
        normalized_value = value.strip()
        normalized_value = normalized_value.replace("캅셀", "캡슐").replace("캡셀", "캡슐").replace("캅슐", "캡슐")
        normalized_value = re.sub(r"\s+", "", normalized_value)
        normalized_value = re.sub(r"[^A-Za-z가-힣0-9]", "", normalized_value)
        return normalized_value

    # 약 제형 suffix 제거 - REQ-DRUG-005
    @staticmethod
    def _strip_drug_form_suffix(keyword: str) -> str:
        for suffix in DRUG_FORM_SUFFIXES:
            if keyword.endswith(suffix) and len(keyword) > len(suffix) + 1:
                return keyword[: -len(suffix)]
        return keyword

    # 캐시 검색 키워드 후보 생성 - REQ-DRUG-001, REQ-DRUG-005
    def _build_cache_search_keywords(self, name: str) -> list[str]:
        normalized_name = self._normalize_mfds_keyword(value=name)
        if not normalized_name:
            return []

        candidates = [normalized_name]
        stripped_once = self._strip_drug_form_suffix(keyword=normalized_name)
        if stripped_once and stripped_once != normalized_name:
            candidates.append(stripped_once)

        stripped_twice = self._strip_drug_form_suffix(keyword=stripped_once)
        if stripped_twice and stripped_twice not in candidates:
            candidates.append(stripped_twice)

        without_units = re.sub(r"\d+(?:MG|G|MCG|ML)?", "", normalized_name, flags=re.IGNORECASE)
        if without_units and without_units not in candidates:
            candidates.append(without_units)

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            cleaned_keyword = candidate.strip()
            if len(cleaned_keyword) < 2:
                continue
            if cleaned_keyword in seen:
                continue
            seen.add(cleaned_keyword)
            deduped.append(cleaned_keyword)
        return deduped

    # 부분일치 실패 시 fuzzy 캐시 후보 탐색 - REQ-DRUG-001, REQ-DRUG-005
    async def _find_fuzzy_drug_cache(self, keyword: str) -> DrugInfoCache | None:
        recent_caches = (
            await DrugInfoCache.exclude(drug_name_display__isnull=True)
            .exclude(drug_name_display="")
            .order_by("-updated_at")
            .limit(200)
        )
        if not recent_caches:
            return None

        normalized_keyword = self._normalize_mfds_keyword(value=keyword)
        if not normalized_keyword:
            return None

        best_ratio = 0.0
        best_candidate: DrugInfoCache | None = None
        for cache in recent_caches:
            normalized_display_name = self._normalize_mfds_keyword(value=cache.drug_name_display or "")
            if not normalized_display_name:
                continue
            ratio = SequenceMatcher(None, normalized_keyword, normalized_display_name).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = cache

        if best_candidate and best_ratio >= 0.72:
            return best_candidate
        return None

    # 복약안내 텍스트를 카드 bullet로 분리 - REQ-DRUG-002
    @staticmethod
    def _split_guide_text_to_bullets(text: str | None, fallback_text: str | None) -> list[str]:
        source_text = text or fallback_text or ""
        if not source_text.strip():
            return []

        normalized_text = re.sub(r"<[^>]+>", " ", source_text)
        normalized_text = normalized_text.replace("\r", "\n")
        normalized_text = re.sub(r"[ \t]+", " ", normalized_text).strip()

        raw_chunks = re.split(r"[\n•·]+|(?<=[.!?。])(?=\s|[가-힣A-Za-z0-9])|(?:\d+\.)\s*", normalized_text)
        bullets: list[str] = []
        seen_bullets: set[str] = set()
        for chunk in raw_chunks:
            candidate_text = chunk.strip(" -:;")
            if not candidate_text:
                continue
            if len(candidate_text) < 3:
                continue
            if len(candidate_text) > 140:
                candidate_text = DocumentService._trim_bullet_to_sentence(candidate_text, max_length=140)
            if candidate_text in seen_bullets:
                continue
            seen_bullets.add(candidate_text)
            bullets.append(candidate_text)
            if len(bullets) >= 4:
                break
        return bullets

    @staticmethod
    def _trim_bullet_to_sentence(text: str, max_length: int = 140) -> str:
        if len(text) <= max_length:
            return text

        clipped = text[:max_length].rstrip()
        sentence_matches = list(re.finditer(r"[.!?。]\s*", clipped))
        if sentence_matches:
            sentence_end = sentence_matches[-1].end()
            if sentence_end >= max(30, max_length // 2):
                return clipped[:sentence_end].rstrip()

        return text

    # 확정 약 메모 생성(OCR fallback 용도) - REQ-DOC-007
    def _build_confirmed_med_note(self, extracted_med: ExtractedMed) -> str:
        parts: list[str] = []
        if extracted_med.dosage_text:
            parts.append(f"용량:{extracted_med.dosage_text}")
        if extracted_med.frequency_text:
            parts.append(f"횟수:{extracted_med.frequency_text}")
        if extracted_med.duration_text:
            parts.append(f"기간:{extracted_med.duration_text}")
        if not parts:
            return "처방전 인식 기반 확정"
        return " / ".join(parts)

    @staticmethod
    def _extract_confirmed_med_note_value(*, notes: str, key: str) -> str | None:
        if not notes:
            return None
        matched = re.search(rf"{re.escape(key)}:([^/]+)", notes)
        if not matched:
            return None
        return DocumentService._nullable_str(matched.group(1))

    # 복약안내 복용횟수 추출(추출약 우선) - REQ-DOC-007
    def _coalesce_frequency_text(self, patient_med: PatientMed, extracted_med: ExtractedMed | None) -> str | None:
        if extracted_med and extracted_med.frequency_text:
            return self._normalize_frequency_text_for_storage(extracted_med.frequency_text)

        if not patient_med.notes:
            return None
        match = re.search(r"횟수:([^/]+)", patient_med.notes)
        if match:
            return self._normalize_frequency_text_for_storage(match.group(1))
        return None

    # 복용시간 슬롯 문자열 정규화(아침/점심/저녁/취침 순서 고정) - REQ-DOC-007
    @staticmethod
    def _normalize_frequency_text_for_storage(frequency_text: str | None) -> str | None:
        normalized_text = DocumentService._nullable_str(frequency_text)
        if not normalized_text:
            return None

        normalized_text = normalized_text.replace("취침 전", "취침").replace("취침전", "취침")
        detected_slots: list[str] = []
        for keyword, _ in DOCUMENT_MED_TIME_SLOTS:
            if keyword in normalized_text and keyword not in detected_slots:
                detected_slots.append(keyword)

        if not detected_slots:
            return normalized_text

        base_text = normalized_text
        for keyword, _ in DOCUMENT_MED_TIME_SLOTS:
            base_text = base_text.replace(keyword, " ")
        base_text = base_text.replace("/", " ").replace(",", " ")
        base_text = re.sub(r"\s+", " ", base_text).strip()

        ordered_slot_text = "/".join(detected_slots)
        if not base_text:
            return ordered_slot_text
        return f"{base_text} {ordered_slot_text}".strip()

    # 복약안내 효능 요약 계산 - REQ-DRUG-002
    def _build_efficacy_summary(self, display_name: str, drug_info_cache: DrugInfoCache | None) -> str | None:
        if drug_info_cache:
            if drug_info_cache.efficacy:
                bullets = self._split_guide_text_to_bullets(text=drug_info_cache.efficacy, fallback_text=None)
                return bullets[0] if bullets else drug_info_cache.efficacy[:120]
            return f"{display_name} 처방약 (식약처 품목 매칭, 상세 효능 정보 없음)"
        return f"{display_name} 처방약 (식약처 상세정보 미매칭)"

    # 복약안내 보관방법 계산 - REQ-DRUG-002
    @staticmethod
    def _build_storage_method(drug_info_cache: DrugInfoCache | None) -> str | None:
        if drug_info_cache and drug_info_cache.storage_method:
            return drug_info_cache.storage_method
        return "직사광선/습기를 피하고 실온 보관"

    # OCR 기반 복약방법 fallback 텍스트 생성 - REQ-DOC-007
    def _build_ocr_fallback_instructions_text(self, patient_med: PatientMed, extracted_med: ExtractedMed | None) -> str:
        parts: list[str] = []
        if patient_med.dosage:
            parts.append(f"1회 {patient_med.dosage} 복용")
        if extracted_med and extracted_med.frequency_text:
            parts.append(f"{extracted_med.frequency_text} 복용")
        if extracted_med and extracted_med.duration_text:
            normalized_duration_text = self._normalize_duration_text_for_guide(extracted_med.duration_text)
            if normalized_duration_text:
                parts.append(f"{normalized_duration_text} 동안 복용")
        if not parts and patient_med.notes:
            parts.append(patient_med.notes)
        return "\n".join(parts)

    # OCR 기반 주의사항 fallback 텍스트 생성 - REQ-DOC-007
    def _build_ocr_fallback_precautions_text(self, extracted_med: ExtractedMed | None) -> str:
        if not extracted_med:
            return ""
        parts: list[str] = []
        if extracted_med.frequency_text and "필요" in extracted_med.frequency_text:
            parts.append("필요 시 복용 약으로 과다 복용을 피하세요.")
        if extracted_med.duration_text:
            normalized_duration_text = self._normalize_duration_text_for_guide(extracted_med.duration_text)
            if normalized_duration_text:
                parts.append(f"처방된 기간({normalized_duration_text})을 우선 지켜 복용하세요.")
        return "\n".join(parts)

    # 복약 안내 문구용 기간 텍스트 정규화(숫자-only -> N일) - REQ-DOC-007
    @staticmethod
    def _normalize_duration_text_for_guide(duration_text: str | None) -> str | None:
        normalized_text = DocumentService._nullable_str(duration_text)
        if not normalized_text:
            return None
        if re.fullmatch(r"\d+", normalized_text):
            return f"{normalized_text}일"
        return normalized_text

    # MFDS 미매칭 시 기본 안전 수칙 - REQ-DOC-007
    @staticmethod
    def _build_default_precautions() -> list[str]:
        return [
            "처방전 또는 의사/약사 안내와 다르면 복용 전 재확인하세요.",
            "어지럼증, 발진 등 이상반응이 있으면 복용을 중지하고 상담하세요.",
            "다른 약과 함께 복용 중이면 병용 가능 여부를 확인하세요.",
        ]

    # 처방 일수 추출 - REQ-DOC-007
    def _extract_prescribed_days(self, patient_med: PatientMed, extracted_med: ExtractedMed | None) -> int | None:
        duration_candidates: list[str] = []
        if extracted_med and extracted_med.duration_text:
            duration_candidates.append(extracted_med.duration_text)
        if patient_med.notes:
            duration_candidates.append(patient_med.notes)

        for duration_text in duration_candidates:
            matched = re.search(r"(\d+)\s*(?:일분|일|days?)", duration_text, flags=re.IGNORECASE)
            if matched:
                return int(matched.group(1))
        return None

    # 처방 시작일 계산(문서 생성일 우선) - REQ-DOC-007
    @staticmethod
    def _resolve_prescribed_at_date(patient_med: PatientMed, source_document: Document | None) -> date | None:
        if source_document:
            return source_document.created_at.date()
        if patient_med.confirmed_at:
            return patient_med.confirmed_at.date()
        return None

    # 복용 종료 예정일 계산 - REQ-DOC-007
    @staticmethod
    def _calculate_expected_end_date(prescribed_at: date | None, prescribed_days: int | None) -> date | None:
        if not prescribed_at or not prescribed_days or prescribed_days <= 0:
            return None
        return prescribed_at + timedelta(days=prescribed_days - 1)

    # DUR 경고 매핑(복약안내 상호작용 노출) - REQ-DRUG-011, REQ-DRUG-013
    async def _build_patient_med_interaction_map(self, patient_meds: list[PatientMed]) -> dict[int, list[str]]:
        if not patient_meds:
            return {}

        patient_id = patient_meds[0].patient_id
        patient_med_ids = [patient_med.id for patient_med in patient_meds]
        alerts = (
            await DurAlert.filter(
                patient_id=patient_id,
                is_active=True,
                patient_med_id__in=patient_med_ids,
            )
            .order_by("-created_at")
            .limit(200)
        )

        interaction_map: dict[int, list[str]] = {}
        for alert in alerts:
            alert_message = (alert.message or "").strip()
            if not alert_message:
                continue
            med_alerts = interaction_map.setdefault(alert.patient_med_id, [])
            if alert_message in med_alerts:
                continue
            if len(med_alerts) >= 3:
                continue
            med_alerts.append(alert_message)
        return interaction_map
