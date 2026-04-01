import asyncio
import base64
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from difflib import get_close_matches
from pathlib import Path

import httpx
from fastapi import HTTPException
from starlette import status

from app.core import config
from app.dtos.documents import DocumentOcrRetryResponse
from app.models.documents import Document, ExtractedMed, OcrJob, OcrRawText
from app.models.notification_settings import NotificationSettings
from app.models.notifications import Notification
from app.models.patients import CaregiverPatientLink, Patient
from app.models.users import User
from app.services.barcode import BarcodeService
from app.services.queue_service import enqueue_send_notification

MED_NAME_SUFFIX_PATTERN = "연질캡슐|장용캡슐|경질캡슐|필름코팅정|장용정|서방정|캅셀|캡셀|캅슐|캡슐|정제|정|시럽|세립|과립|현탁액|주사액|주사|크림|로션|패취|패치"
KOREAN_MED_NAME_PATTERN = re.compile(rf"([A-Za-z가-힣0-9+\-/]{{2,}}(?:{MED_NAME_SUFFIX_PATTERN}))")
ENGLISH_MED_WITH_DOSE_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+\-/]{2,})\b\s*(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|mL))",
    re.IGNORECASE,
)
DOSAGE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|mL|정|캡슐|T))\b", re.IGNORECASE)
FREQUENCY_PATTERN = re.compile(
    r"(1일\s*\d+\s*회|하루\s*\d+\s*회|매일\s*\d+\s*회|\d+\s*회|아침|점심|저녁|취침\s*전|필요\s*시|PRN)",
    re.IGNORECASE,
)
DURATION_PATTERN = re.compile(r"(\d+\s*(?:일분|일|주|개월)(?:간)?)")
SUMMARY_FREQUENCY_LABEL_PATTERN = re.compile(r"(?:1일\s*)?(?:투여)?횟수\s*[:：]?\s*(\d+)", re.IGNORECASE)
SUMMARY_DURATION_LABEL_PATTERN = re.compile(
    r"(?:총\s*)?(?:투약(?:일수|기간)|총투약(?:일수|기간)|처방일수)\s*[:：]?\s*(\d+)",
    re.IGNORECASE,
)
COUNT_DOSAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?\s*(?:(?:정|캡슐|알|포)(?:씩)?|T))")
PACKED_SCHEDULE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(정|캡슐|알|포|ml|mL)?\s*씩?\s*(\d+)\s*회\s*(\d+)\s*(?:일분|일)",
    re.IGNORECASE,
)
PACKED_NUMERIC_ROW_PATTERN = re.compile(
    r"^(?P<dose_count>\d+(?:\.\d+)?)\s*(?P<dose_unit>정|캡슐|알|포|ml|mL)?\s*(?:씩)?\s+"
    r"(?P<frequency_count>\d+)\s*(?:회)?\s+"
    r"(?P<duration_days>\d+)\s*(?:일분|일)?$",
    re.IGNORECASE,
)
SIMPLE_DOSAGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(정|캡슐|알|포|ml|mL)\s*씩?", re.IGNORECASE)
SIMPLE_FREQUENCY_PATTERN = re.compile(r"(\d+)\s*회")
SIMPLE_DURATION_PATTERN = re.compile(r"(\d+)\s*(일분|일)")
NOISE_KEYWORDS = {
    "[barcode_detections]",
    "type=",
    "환자정보",
    "병원정보",
    "복약안내",
    "조제약사",
    "조제일자",
    "영수증",
    "계산서",
    "약제비",
    "약제비총액",
    "본인부담금",
    "보험자부담금",
    "총수납금액",
    "현금영수증",
    "현금승인번호",
    "신분확인번호",
    "사업장소재지",
    "사업자등록번호",
    "전화",
    "처방전",
    "약품사진",
    "약국",
    "보험",
    "수납",
    "금액",
    "본인전액",
    "공제신청",
    "요구할 수 있습니다",
}
GENERIC_MED_NAMES = {
    "필름코팅정",
    "변형정",
    "장용정",
    "서방정",
    "연질캡슐",
    "장용캡슐",
    "캡슐",
    "정",
    "주",
    "액",
    "겔",
    "시럽",
    "세립",
    "과립",
    "크림",
    "로션",
}
MED_DESCRIPTOR_KEYWORDS = {
    "백색",
    "황색",
    "청색",
    "갈색",
    "담녹색",
    "암녹색",
    "연한",
    "진한",
    "분말",
    "원형",
    "타원형",
    "장방형",
    "정제",
    "경질",
    "연질",
    "필름코팅",
    "완화시켜",
    "배출되도록",
    "약입니다",
}
NON_MED_NAME_KEYWORDS = {
    "약제비",
    "총액",
    "영수증",
    "본인부담금",
    "보험자부담금",
    "본인전액",
    "수납",
    "금액",
    "공제",
    "사업자",
    "신분확인",
    "현금승인",
    "조제약사",
    "병원정보",
    "환자정보",
    "조제일자",
    "복약안내",
    "약품사진",
    "약품명",
    "투약량",
    "횟수",
    "일수",
    "총투",
    "계산",
}
MED_NAME_OCR_CORRECTIONS = {
    "메디락디에스장용캅셀": "메디락디에스장용캡슐",
    "메디락디에스장용캡셀": "메디락디에스장용캡슐",
    "메디락디에스장용캅슐": "메디락디에스장용캡슐",
    "텔미누보정40/5m": "텔미누보정40/5mg",
}

logger = logging.getLogger(__name__)


class OcrService:
    def __init__(self):
        self.project_root = Path(__file__).resolve().parents[2]
        self.barcode_service = BarcodeService()

    # REQ-DOC-008 - OCR 재시도 요청 처리
    async def retry_document_ocr(self, user: User, document_id: int) -> DocumentOcrRetryResponse:
        document = await Document.filter(id=document_id, status="uploaded").first()
        if not document:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NOT_FOUND")

        if not await self._has_patient_access(user=user, patient_id=document.patient_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="FORBIDDEN")

        latest_job = await OcrJob.filter(document_id=document.id).order_by("-created_at").first()
        if latest_job and latest_job.status == "processing":
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="UNPROCESSABLE")
        if latest_job and latest_job.status == "queued":
            # REQ-DOC-008 - 대기중 job이 남아있으면 해당 job을 재실행 트리거
            asyncio.create_task(self.process_ocr_job(ocr_job_id=latest_job.id))
            return DocumentOcrRetryResponse(
                document_id=document.id,
                ocr_job_id=latest_job.id,
                status=latest_job.status,
                retry_count=latest_job.retry_count,
                queued_at=latest_job.created_at,
            )

        next_retry_count = (latest_job.retry_count + 1) if latest_job else 0
        ocr_job = await OcrJob.create(
            document_id=document.id,
            patient_id=document.patient_id,
            status="queued",
            retry_count=next_retry_count,
            error_code=None,
            error_message=None,
        )

        # REQ-DOC-003 - 비동기 OCR 실행 트리거
        asyncio.create_task(self.process_ocr_job(ocr_job_id=ocr_job.id))

        return DocumentOcrRetryResponse(
            document_id=document.id,
            ocr_job_id=ocr_job.id,
            status=ocr_job.status,
            retry_count=ocr_job.retry_count,
            queued_at=ocr_job.created_at,
        )

    # 서버 재시작 시 미완료 OCR 작업 자동 재개 - REQ-DOC-003, REQ-DOC-008
    async def resume_pending_ocr_jobs(self, max_jobs: int = 50) -> int:
        if max_jobs <= 0:
            return 0

        pending_jobs = await OcrJob.filter(
            status__in=["queued", "processing"],
            document__status="uploaded",
        ).order_by("-created_at")

        selected_jobs: list[OcrJob] = []
        seen_document_ids: set[int] = set()
        for pending_job in pending_jobs:
            if pending_job.document_id in seen_document_ids:
                continue
            seen_document_ids.add(pending_job.document_id)
            selected_jobs.append(pending_job)
            if len(selected_jobs) >= max_jobs:
                break

        # 오래된 요청부터 순서대로 재개 트리거
        for selected_job in reversed(selected_jobs):
            asyncio.create_task(self.process_ocr_job(ocr_job_id=selected_job.id))
        return len(selected_jobs)

    # REQ-DOC-005 - 기존 성공 OCR job 원문으로 추출 약 데이터 백필
    async def backfill_extracted_meds(self, ocr_job_id: int) -> int:
        ocr_job = await OcrJob.get_or_none(id=ocr_job_id)
        if not ocr_job:
            return 0

        raw_text_row = await OcrRawText.get_or_none(ocr_job_id=ocr_job_id)
        if not raw_text_row or not raw_text_row.raw_text.strip():
            logger.info("OCR backfill skipped: no raw_text (ocr_job_id=%s)", ocr_job_id)
            return await ExtractedMed.filter(ocr_job_id=ocr_job_id).count()

        await self._save_extracted_meds(
            ocr_job_id=ocr_job_id,
            patient_id=ocr_job.patient_id,
            raw_text=raw_text_row.raw_text,
        )
        return await ExtractedMed.filter(ocr_job_id=ocr_job_id).count()

    # REQ-DOC-003, REQ-DOC-004, REQ-DOC-005, REQ-DOC-009 - OCR 비동기 처리 본체
    async def process_ocr_job(self, ocr_job_id: int) -> None:
        ocr_job = await OcrJob.filter(id=ocr_job_id).select_related("document").first()
        if not ocr_job:
            return

        await OcrJob.filter(id=ocr_job.id).update(
            status="processing",
            error_code=None,
            error_message=None,
        )

        try:
            # REQ-DOC-009 - 바코드 인식 우선 시도
            barcode_text = await self._extract_barcode_text(document=ocr_job.document)

            # REQ-DOC-004, REQ-DOC-009 - OCR 텍스트 + 바코드 텍스트 결합
            raw_text, ocr_fields = await self._build_combined_raw_text(
                document=ocr_job.document,
                barcode_text=barcode_text,
            )
            await self._save_raw_text(ocr_job_id=ocr_job.id, raw_text=raw_text)

            # REQ-DOC-005 - OCR 원문 기반 약 정보 구조화 저장
            await self._save_extracted_meds(
                ocr_job_id=ocr_job.id,
                patient_id=ocr_job.patient_id,
                raw_text=raw_text,
                ocr_fields=ocr_fields,
            )

            await OcrJob.filter(id=ocr_job.id).update(status="success")
            try:
                await self._notify_ocr_done(ocr_job=ocr_job)
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            await OcrJob.filter(id=ocr_job.id).update(
                status="failed",
                error_code=self._build_error_code(exc),
                error_message=str(exc)[:1000],
            )
            try:
                await self._notify_ocr_failed(ocr_job=ocr_job, error_message=str(exc))
            except Exception:
                pass

    async def _notify_ocr_done(self, ocr_job: OcrJob) -> None:
        patient = await Patient.filter(id=ocr_job.patient_id).prefetch_related("caregiver_links").first()
        if not patient:
            return

        recipients: set[int] = set()
        if patient.user_id:
            recipients.add(int(patient.user_id))

        for link in getattr(patient, "caregiver_links", []):
            if getattr(link, "status", None) != "active" or getattr(link, "revoked_at", None) is not None:
                continue
            caregiver_user_id = getattr(link, "caregiver_user_id", None)
            if caregiver_user_id:
                recipients.add(int(caregiver_user_id))

        if not recipients:
            return

        reminder_key = f"ocr_done:{ocr_job.document_id}:{ocr_job.id}"
        document_title = (ocr_job.document.original_filename or "").strip() if ocr_job.document else ""
        title = "OCR 분석이 완료되었어요"
        body = (
            f"{document_title} 문서의 약 정보 추출이 완료되었어요."
            if document_title
            else "업로드한 문서의 약 정보 추출이 완료되었어요."
        )
        payload = {
            "document_id": ocr_job.document_id,
            "ocr_job_id": ocr_job.id,
            "patient_id": ocr_job.patient_id,
            "reminder_key": reminder_key,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        for user_id in recipients:
            if not await self._is_ocr_done_notification_enabled(user_id):
                continue

            if await self._ocr_done_notification_exists(user_id=user_id, reminder_key=reminder_key):
                continue

            notification = await Notification.create(
                user_id=user_id,
                patient_id=ocr_job.patient_id,
                type="ocr_done",
                title=title,
                body=body,
                payload_json=payload_json,
                sent_at=None,
            )
            await enqueue_send_notification(notification.id)

    async def _notify_ocr_failed(self, *, ocr_job: OcrJob, error_message: str) -> None:
        uploaded_by_user_id = getattr(ocr_job.document, "uploaded_by_user_id", None) if ocr_job.document else None
        if not uploaded_by_user_id:
            return

        if not await self._is_ocr_done_notification_enabled(int(uploaded_by_user_id)):
            return

        reminder_key = f"ocr_failed:{ocr_job.document_id}:{ocr_job.id}"
        if await self._notification_exists(
            user_id=int(uploaded_by_user_id),
            notification_type="ocr_failed",
            reminder_key=reminder_key,
        ):
            return

        document_title = (ocr_job.document.original_filename or "").strip() if ocr_job.document else ""
        title = "OCR 분석에 실패했어요"
        body = (
            f"{document_title} 문서 분석에 실패했어요. 다시 시도해 주세요."
            if document_title
            else "업로드한 문서 분석에 실패했어요. 다시 시도해 주세요."
        )
        payload = {
            "document_id": ocr_job.document_id,
            "ocr_job_id": ocr_job.id,
            "patient_id": ocr_job.patient_id,
            "error_message": error_message[:300],
            "reminder_key": reminder_key,
        }
        payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        notification = await Notification.create(
            user_id=int(uploaded_by_user_id),
            patient_id=ocr_job.patient_id,
            type="ocr_failed",
            title=title,
            body=body,
            payload_json=payload_json,
            sent_at=None,
        )
        await enqueue_send_notification(notification.id)

    @staticmethod
    async def _is_ocr_done_notification_enabled(user_id: int) -> bool:
        settings = await NotificationSettings.get_or_none(user_id=user_id)
        if settings is None:
            return True
        return bool(settings.ocr_done)

    @staticmethod
    async def _notification_exists(*, user_id: int, notification_type: str, reminder_key: str) -> bool:
        return await Notification.filter(
            user_id=user_id,
            type=notification_type,
            payload_json__contains=f'"reminder_key":"{reminder_key}"',
        ).exists()

    @classmethod
    async def _ocr_done_notification_exists(cls, *, user_id: int, reminder_key: str) -> bool:
        return await cls._notification_exists(
            user_id=user_id,
            notification_type="ocr_done",
            reminder_key=reminder_key,
        )

    # REQ-DOC-004, REQ-DOC-009 - OCR 원문/바코드 결과 결합
    async def _build_combined_raw_text(
        self, document: Document, barcode_text: str
    ) -> tuple[str, list[dict[str, str | float]]]:
        raw_text_parts: list[str] = []
        if barcode_text:
            raw_text_parts.append(barcode_text.strip())

        ocr_text = ""
        ocr_fields: list[dict[str, str | float]] = []
        try:
            ocr_text, ocr_fields = await self._request_naver_ocr(document=document)
        except RuntimeError as exc:
            # 바코드가 이미 있으면 OCR 공백/설정 누락 케이스는 fallback 허용
            if not raw_text_parts or str(exc) not in {"OCR_EMPTY_RESULT", "NAVER_OCR_CONFIG_MISSING"}:
                raise

        if ocr_text:
            raw_text_parts.append(ocr_text.strip())

        raw_text = "\n".join(part for part in raw_text_parts if part).strip()
        if not raw_text:
            raise RuntimeError("OCR_EMPTY_RESULT")
        return raw_text, ocr_fields

    # REQ-DOC-009 - 바코드 인식 결과 추출
    async def _extract_barcode_text(self, document: Document) -> str:
        file_path = self.project_root / document.file_url
        detections = await asyncio.to_thread(self.barcode_service.extract_from_file, file_path)
        if not detections:
            return ""

        lines = ["[BARCODE_DETECTIONS]"]
        for detection in detections:
            lines.append(f"type={detection.barcode_type}, value={detection.barcode_value}")
        return "\n".join(lines)

    # REQ-DOC-003 - 네이버 OCR API 호출
    async def _request_naver_ocr(  # noqa: C901
        self, document: Document
    ) -> tuple[str, list[dict[str, str | float]]]:
        if not config.NAVER_OCR_API_URL or not config.NAVER_OCR_SECRET_KEY:
            raise RuntimeError("NAVER_OCR_CONFIG_MISSING")

        file_path = self.project_root / document.file_url
        if not file_path.exists():
            raise RuntimeError("OCR_FILE_NOT_FOUND")

        file_bytes = file_path.read_bytes()
        if not file_bytes:
            raise RuntimeError("OCR_FILE_EMPTY")

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            file_format = "pdf"
        elif suffix == ".png":
            file_format = "png"
        else:
            file_format = "jpg"
        payload = {
            "version": "V2",
            "requestId": uuid.uuid4().hex,
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
            "images": [
                {
                    "format": file_format,
                    "name": file_path.stem or "document",
                    "data": base64.b64encode(file_bytes).decode("utf-8"),
                }
            ],
        }

        headers = {
            "X-OCR-SECRET": config.NAVER_OCR_SECRET_KEY,
            "Content-Type": "application/json",
        }

        timeout = httpx.Timeout(config.NAVER_OCR_TIMEOUT_SECONDS)
        max_retries = max(0, int(config.NAVER_OCR_MAX_RETRIES))
        base_backoff_seconds = max(0.0, float(config.NAVER_OCR_RETRY_BACKOFF_SECONDS))
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(max_retries + 1):
                try:
                    response = await client.post(config.NAVER_OCR_API_URL, headers=headers, json=payload)
                except (httpx.TimeoutException, httpx.TransportError):
                    if attempt >= max_retries:
                        raise
                    await asyncio.sleep(
                        self._build_naver_ocr_retry_delay_seconds(
                            attempt=attempt,
                            base_backoff_seconds=base_backoff_seconds,
                        )
                    )
                    continue

                if response.status_code >= status.HTTP_400_BAD_REQUEST:
                    runtime_error = RuntimeError(f"NAVER_OCR_HTTP_{response.status_code}")
                    if attempt < max_retries and self._is_retryable_naver_ocr_http_status(response.status_code):
                        await asyncio.sleep(
                            self._build_naver_ocr_retry_delay_seconds(
                                attempt=attempt,
                                base_backoff_seconds=base_backoff_seconds,
                            )
                        )
                        continue
                    raise runtime_error

                data = response.json()
                ocr_fields = self._extract_ocr_fields(data=data)
                raw_text = self._extract_raw_text(data=data)
                if not raw_text and ocr_fields:
                    raw_text = "\n".join(
                        str(field["text"]).strip() for field in ocr_fields if str(field.get("text") or "").strip()
                    )
                if not raw_text:
                    raise RuntimeError("OCR_EMPTY_RESULT")
                return raw_text, ocr_fields

        raise RuntimeError("OCR_RETRY_EXHAUSTED")

    @staticmethod
    def _is_retryable_naver_ocr_http_status(status_code: int) -> bool:
        return status_code == status.HTTP_429_TOO_MANY_REQUESTS or status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR

    @staticmethod
    def _build_naver_ocr_retry_delay_seconds(*, attempt: int, base_backoff_seconds: float) -> float:
        if base_backoff_seconds <= 0:
            return 0.0
        safe_attempt = max(0, min(attempt, 6))
        return base_backoff_seconds * (2**safe_attempt)

    # REQ-DOC-004 - OCR 원문 텍스트 추출
    @staticmethod
    def _extract_raw_text(data: dict) -> str:
        images = data.get("images") or []
        if not images:
            return ""

        fields = images[0].get("fields") or []
        texts = [str(field.get("inferText", "")).strip() for field in fields if str(field.get("inferText", "")).strip()]
        return "\n".join(texts).strip()

    # REQ-DOC-004 - OCR fields + bbox 좌표 추출
    @staticmethod
    def _extract_ocr_fields(data: dict) -> list[dict[str, str | float]]:
        images = data.get("images") or []
        if not images:
            return []

        raw_fields = images[0].get("fields") or []
        extracted_fields: list[dict[str, str | float]] = []
        for raw_field in raw_fields:
            text = str(raw_field.get("inferText", "")).strip()
            if not text:
                continue

            vertices = (raw_field.get("boundingPoly") or {}).get("vertices") or []
            points: list[tuple[float, float]] = []
            for vertex in vertices:
                try:
                    point_x = float(vertex.get("x", 0))
                    point_y = float(vertex.get("y", 0))
                except (TypeError, ValueError):
                    point_x = 0.0
                    point_y = 0.0
                points.append((point_x, point_y))

            if not points:
                x_min = x_max = y_min = y_max = 0.0
            else:
                x_values = [point[0] for point in points]
                y_values = [point[1] for point in points]
                x_min = min(x_values)
                x_max = max(x_values)
                y_min = min(y_values)
                y_max = max(y_values)

            extracted_fields.append(
                {
                    "text": text,
                    "x_min": x_min,
                    "x_max": x_max,
                    "y_min": y_min,
                    "y_max": y_max,
                    "cx": (x_min + x_max) / 2,
                    "cy": (y_min + y_max) / 2,
                }
            )
        return extracted_fields

    # REQ-DOC-004 - OCR 원문 저장
    async def _save_raw_text(self, ocr_job_id: int, raw_text: str) -> None:
        existing_raw_text = await OcrRawText.get_or_none(ocr_job_id=ocr_job_id)
        if existing_raw_text:
            await OcrRawText.filter(id=existing_raw_text.id).update(raw_text=raw_text)
            return
        await OcrRawText.create(ocr_job_id=ocr_job_id, raw_text=raw_text)

    # REQ-DOC-005 - OCR 원문 기반 약 정보 구조화 저장
    async def _save_extracted_meds(
        self,
        ocr_job_id: int,
        patient_id: int,
        raw_text: str,
        ocr_fields: list[dict[str, str | float]] | None = None,
    ) -> None:
        parsed_meds = self._parse_extracted_meds(raw_text=raw_text, ocr_fields=ocr_fields)

        await ExtractedMed.filter(ocr_job_id=ocr_job_id).delete()
        for parsed_med in parsed_meds:
            await ExtractedMed.create(
                ocr_job_id=ocr_job_id,
                patient_id=patient_id,
                name=parsed_med["name"],
                dosage_text=parsed_med["dosage_text"],
                frequency_text=parsed_med["frequency_text"],
                duration_text=parsed_med["duration_text"],
                confidence=parsed_med["confidence"],
            )

    # REQ-DOC-005 - OCR 원문 파싱(약명/용량/횟수/기간 구조화)
    def _parse_extracted_meds(
        self, raw_text: str, ocr_fields: list[dict[str, str | float]] | None = None
    ) -> list[dict[str, str | float | None]]:
        lines = [self._normalize_line(line) for line in raw_text.splitlines()]
        lines = [line for line in lines if line]

        if ocr_fields:
            logger.info("OCR meds parse: trying simple field parser (fields=%d)", len(ocr_fields))
            simple_field_meds = self._parse_extracted_meds_simple_from_ocr_fields(ocr_fields=ocr_fields)
            if simple_field_meds:
                logger.info("OCR meds parse: simple field parser selected (count=%d)", len(simple_field_meds))
                return simple_field_meds

            logger.info("OCR meds parse: simple parser empty, fallback to legacy field parser")
            field_based_meds = self._parse_extracted_meds_from_ocr_fields(ocr_fields=ocr_fields)
            if field_based_meds:
                logger.info("OCR meds parse: legacy field parser selected (count=%d)", len(field_based_meds))
                return field_based_meds

            logger.info("OCR meds parse: legacy field parser empty, fallback to regex parser")
        return self._parse_extracted_meds_with_regex(lines=lines)

    # REQ-DOC-005 - 정규식 기반 OCR fallback 파싱
    def _parse_extracted_meds_with_regex(self, lines: list[str]) -> list[dict[str, str | float | None]]:  # noqa: C901
        if not lines:
            return []

        summary_med_names = self._extract_summary_med_names(lines=lines)
        summary_schedule_map = self._extract_summary_schedule_map(lines=lines, summary_med_names=summary_med_names)
        lines = self._extract_medication_section_lines(lines=lines)
        lines = [line for line in lines if not self._is_noise_line(line)]

        parsed_meds: list[dict[str, str | float | None]] = []
        seen_names: set[str] = set()

        for idx, line in enumerate(lines):
            context_window = lines[idx : idx + 3]
            context_line = " ".join(context_window).strip()
            line_for_name = re.split(r"\[", line, maxsplit=1)[0].strip()
            if self._is_descriptor_heavy_line(line=line_for_name):
                continue

            packed_schedule_match = PACKED_SCHEDULE_PATTERN.search(context_line)
            packed_dosage_text = None
            packed_frequency_text = None
            packed_duration_text = None
            if packed_schedule_match:
                packed_dose_count = packed_schedule_match.group(1).strip()
                packed_dose_unit = (packed_schedule_match.group(2) or "").strip().lower()
                packed_frequency_count = packed_schedule_match.group(3).strip()
                packed_duration_days = packed_schedule_match.group(4).strip()
                packed_dosage_text = self._build_dosage_text_from_count(
                    med_name=line_for_name,
                    dose_count=packed_dose_count,
                    explicit_unit=packed_dose_unit,
                )
                packed_frequency_text = self._normalize_frequency_text(raw_text=f"{packed_frequency_count}회")
                packed_duration_text = f"{packed_duration_days}일분"

            dosage_text = self._extract_first(line=context_line, pattern=DOSAGE_PATTERN) or self._extract_first(
                line=context_line, pattern=COUNT_DOSAGE_PATTERN
            )
            frequency_text = self._extract_frequency_text_from_context(context_line=context_line)
            duration_text = self._extract_duration_text_from_context(context_line=context_line)

            for name in KOREAN_MED_NAME_PATTERN.findall(line_for_name):
                split_name, strength_text = self._split_med_name_and_strength(text=name)
                normalized_name = self._sanitize_extracted_med_name(name=split_name)
                if not self._is_valid_med_name(name=normalized_name):
                    continue

                dedupe_key = normalized_name.casefold()
                if dedupe_key in seen_names:
                    continue
                seen_names.add(dedupe_key)
                strength_dosage_text = self._normalize_line(strength_text) if strength_text else None

                schedule_from_summary = self._find_schedule_from_summary(
                    med_name=normalized_name,
                    summary_schedule_map=summary_schedule_map,
                )

                parsed_meds.append(
                    {
                        "name": normalized_name,
                        "dosage_text": self._resolve_dosage_text_for_output(
                            dosage_text=dosage_text or strength_dosage_text,
                            packed_dosage_text=packed_dosage_text,
                            schedule_from_summary=schedule_from_summary,
                        ),
                        "frequency_text": (
                            frequency_text
                            or packed_frequency_text
                            or (schedule_from_summary["frequency_text"] if schedule_from_summary else None)
                        ),
                        "duration_text": (
                            duration_text
                            or packed_duration_text
                            or (schedule_from_summary["duration_text"] if schedule_from_summary else None)
                        ),
                        "confidence": 0.90 if dosage_text else 0.82,
                    }
                )

            # 한국어 제형 패턴으로 못 잡을 때 영문+용량 패턴 fallback
            for match in ENGLISH_MED_WITH_DOSE_PATTERN.findall(line_for_name):
                normalized_name = self._sanitize_extracted_med_name(name=match[0])
                if not self._is_valid_med_name(name=normalized_name):
                    continue

                dedupe_key = normalized_name.casefold()
                if dedupe_key in seen_names:
                    continue
                seen_names.add(dedupe_key)

                schedule_from_summary = self._find_schedule_from_summary(
                    med_name=normalized_name,
                    summary_schedule_map=summary_schedule_map,
                )

                parsed_meds.append(
                    {
                        "name": normalized_name,
                        "dosage_text": self._resolve_dosage_text_for_output(
                            dosage_text=(self._normalize_line(match[1]) or dosage_text),
                            packed_dosage_text=packed_dosage_text,
                            schedule_from_summary=schedule_from_summary,
                        ),
                        "frequency_text": frequency_text
                        or packed_frequency_text
                        or (schedule_from_summary["frequency_text"] if schedule_from_summary else None),
                        "duration_text": duration_text
                        or packed_duration_text
                        or (schedule_from_summary["duration_text"] if schedule_from_summary else None),
                        "confidence": 0.80,
                    }
                )

        # OCR 오탐(영수증/설명 문구 등) 최소화 - REQ-DOC-005
        parsed_meds = [med for med in parsed_meds if self._is_useful_parsed_med(parsed_med=med)]

        if summary_med_names:
            parsed_meds = self._filter_parsed_meds_with_summary(
                parsed_meds=parsed_meds,
                summary_med_names=summary_med_names,
                summary_schedule_map=summary_schedule_map,
            )

        self._apply_packed_schedule_fallback(parsed_meds=parsed_meds, lines=lines)
        return parsed_meds

    # REQ-DOC-005 - 단순 bbox row 기반 OCR field parser(약 개수 보존 우선)
    def _parse_extracted_meds_simple_from_ocr_fields(  # noqa: C901
        self, ocr_fields: list[dict[str, str | float]]
    ) -> list[dict[str, str | float | None]]:
        if not ocr_fields:
            return []

        logger.info("OCR simple parser: start (fields=%d)", len(ocr_fields))
        layout = self._segment_layout_regions(ocr_fields=ocr_fields)
        med_guide_fields = layout.get("med_guide_fields") or []
        summary_fields = layout.get("summary_fields") or []

        summary_lines = self._fields_to_lines(fields=summary_fields)
        if not summary_lines:
            summary_lines = self._fields_to_lines(fields=ocr_fields)
        summary_med_names = self._extract_summary_med_names(lines=summary_lines)
        summary_schedule_map = self._extract_summary_schedule_map(
            lines=summary_lines,
            summary_med_names=summary_med_names,
        )
        if not med_guide_fields:
            logger.info("OCR simple parser: med_guide_fields not found")
            return []

        med_guide_threshold = self._estimate_row_y_threshold(
            fields=med_guide_fields,
            factor=0.32,
            min_value=3.5,
            max_value=8.0,
        )
        med_guide_rows = self._group_fields_into_rows(fields=med_guide_fields, y_threshold=med_guide_threshold)
        logger.info("OCR simple parser: grouped rows=%d", len(med_guide_rows))

        blocks = self._build_simple_medication_blocks(rows=med_guide_rows)
        logger.info("OCR simple parser: medication blocks=%d", len(blocks))
        if not blocks:
            return []

        parsed_meds: list[dict[str, str | float | None]] = []
        for block_idx, block in enumerate(blocks):
            med_name_candidate: tuple[str, str | None] | None = None
            med_rows = block.get("med_rows") or []
            row_texts = block.get("row_texts") or []
            guide_rows = block.get("guide_rows") or []

            for candidate_text in [*med_rows, *row_texts]:
                med_name_candidate = self._extract_simple_med_name_from_text(text=str(candidate_text))
                if med_name_candidate:
                    break

            if not med_name_candidate:
                logger.debug("OCR simple parser block[%d]: skipped (no med name candidate)", block_idx)
                continue

            med_name, strength_text = med_name_candidate
            dosage_text: str | None = None
            frequency_text: str | None = None
            duration_text: str | None = None

            for schedule_source in [*guide_rows, *row_texts]:
                schedule = self._extract_simple_schedule_from_text(text=str(schedule_source))
                if not schedule:
                    continue
                if not dosage_text and schedule.get("dosage_text"):
                    dosage_text = schedule["dosage_text"]
                if not frequency_text and schedule.get("frequency_text"):
                    frequency_text = schedule["frequency_text"]
                if not duration_text and schedule.get("duration_text"):
                    duration_text = schedule["duration_text"]
                if dosage_text and frequency_text and duration_text:
                    break

            # 가이드에서 1정씩/1캡슐씩을 우선 적용하고, 없으면 약명 strength(mg)를 보조로 사용
            if not dosage_text and strength_text:
                dosage_text = self._normalize_line(strength_text)

            confidence = 0.88 if (frequency_text and duration_text) else 0.80
            if not any([dosage_text, frequency_text, duration_text]):
                confidence = 0.74

            parsed_meds.append(
                {
                    "name": med_name,
                    "dosage_text": dosage_text,
                    "frequency_text": frequency_text,
                    "duration_text": duration_text,
                    "confidence": confidence,
                }
            )
            logger.debug(
                "OCR simple parser block[%d]: name=%s dosage=%s frequency=%s duration=%s",
                block_idx,
                med_name,
                dosage_text,
                frequency_text,
                duration_text,
            )

        deduped_meds: list[dict[str, str | float | None]] = []
        seen_names: set[str] = set()
        for parsed_med in parsed_meds:
            med_name = str(parsed_med.get("name") or "")
            compare_key = self._normalize_name_for_compare(name=med_name)
            if not compare_key:
                continue
            if compare_key in seen_names:
                continue
            seen_names.add(compare_key)
            deduped_meds.append(parsed_med)

        logger.info(
            "OCR simple parser: extracted=%d deduped=%d",
            len(parsed_meds),
            len(deduped_meds),
        )
        if deduped_meds:
            self._merge_schedule_from_summary(
                parsed_meds=deduped_meds,
                summary_schedule_map=summary_schedule_map,
            )
        if config.OCR_ENABLE_SUMMARY_AUGMENT_FOR_MED_GUIDE and summary_med_names:
            deduped_meds = self._filter_parsed_meds_with_summary(
                parsed_meds=deduped_meds,
                summary_med_names=summary_med_names,
                summary_schedule_map=summary_schedule_map,
            )
            logger.info("OCR simple parser: summary-augmented count=%d", len(deduped_meds))
        return deduped_meds

    # REQ-DOC-005 - 단순 parser용 medication block 구성
    def _build_simple_medication_blocks(  # noqa: C901
        self,
        *,
        rows: list[list[dict[str, str | float]]],
    ) -> list[dict[str, list[str]]]:
        if not rows:
            return []

        row_lines = [self._normalize_line(self._build_row_text(row_fields=row_fields)) for row_fields in rows]
        header_idx: int | None = None
        split_x: float | None = None
        for idx, row_fields in enumerate(rows):
            med_header = next((field for field in row_fields if "약품명" in str(field.get("text", ""))), None)
            guide_header = next((field for field in row_fields if "복약안내" in str(field.get("text", ""))), None)
            if med_header and guide_header:
                header_idx = idx
                split_x = (float(med_header.get("cx", 0.0)) + float(guide_header.get("cx", 0.0))) / 2
                break

        if header_idx is None or split_x is None:
            return []

        blocks: list[dict[str, list[str]]] = []
        current_block: dict[str, list[str]] | None = None
        body_rows = rows[header_idx + 1 :]
        body_lines = row_lines[header_idx + 1 :]

        for idx, row_fields in enumerate(body_rows):
            row_text = (
                body_lines[idx] if idx < len(body_lines) else self._normalize_line(self._build_row_text(row_fields))
            )
            if not row_text:
                continue
            if self._is_summary_header_row_text(current_line=row_text, next_lines=body_lines[idx + 1 : idx + 6]):
                break

            med_text = self._normalize_line(
                " ".join(
                    str(field.get("text", "")).strip()
                    for field in row_fields
                    if float(field.get("cx", 0.0)) <= split_x and str(field.get("text", "")).strip()
                )
            )
            guide_text = self._normalize_line(
                " ".join(
                    str(field.get("text", "")).strip()
                    for field in row_fields
                    if float(field.get("cx", 0.0)) > split_x and str(field.get("text", "")).strip()
                )
            )

            candidate_source = med_text or row_text
            has_new_med = bool(self._extract_simple_med_name_from_text(text=candidate_source))
            if has_new_med:
                current_block = {
                    "med_rows": [candidate_source],
                    "guide_rows": [guide_text] if guide_text else [],
                    "row_texts": [row_text],
                }
                blocks.append(current_block)
                continue

            if current_block is None:
                continue

            current_block["row_texts"].append(row_text)
            if med_text:
                current_block["med_rows"].append(med_text)
            if guide_text:
                current_block["guide_rows"].append(guide_text)

        return blocks

    # REQ-DOC-005 - 단순 parser용 약명 추출(제형 suffix + optional strength)
    def _extract_simple_med_name_from_text(self, text: str) -> tuple[str, str | None] | None:
        normalized_text = self._normalize_line(text)
        if not normalized_text:
            return None

        med_match = re.search(
            rf"(?P<name>[A-Za-z가-힣0-9+\-/]{{2,}}(?:{MED_NAME_SUFFIX_PATTERN}))\s*"
            rf"(?P<strength>\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|mL))?",
            normalized_text,
            flags=re.IGNORECASE,
        )
        if not med_match:
            return None

        med_name = self._sanitize_extracted_med_name(name=med_match.group("name"))
        if not med_name:
            return None

        compact_name = re.sub(r"\s+", "", med_name)
        if self._contains_non_med_keyword(compact_name=compact_name):
            return None
        if self._is_suspicious_generic_med_name(name=compact_name):
            return None
        if not re.search(r"[A-Za-z가-힣]", compact_name):
            return None

        strength_text = self._normalize_line(med_match.group("strength")) if med_match.group("strength") else None
        return med_name, strength_text

    # REQ-DOC-005 - 단순 parser용 복약안내 추출(~씩 / ~회 / ~일분)
    def _extract_simple_schedule_from_text(self, text: str) -> dict[str, str | None] | None:
        normalized_text = self._normalize_line(text)
        if not normalized_text:
            return None

        dosage_match = SIMPLE_DOSAGE_PATTERN.search(normalized_text)
        frequency_match = SIMPLE_FREQUENCY_PATTERN.search(normalized_text)
        duration_match = SIMPLE_DURATION_PATTERN.search(normalized_text)
        if not any([dosage_match, frequency_match, duration_match]):
            return None

        dosage_text: str | None = None
        if dosage_match:
            dose_count = dosage_match.group(1).strip()
            dose_unit = dosage_match.group(2).strip()
            if dose_unit.lower() == "ml":
                dose_unit = "ml"
            dosage_text = f"{dose_count}{dose_unit}씩"

        frequency_text = f"{frequency_match.group(1).strip()}회" if frequency_match else None
        duration_text = f"{duration_match.group(1).strip()}일분" if duration_match else None
        return {
            "dosage_text": dosage_text,
            "frequency_text": frequency_text,
            "duration_text": duration_text,
        }

    # REQ-DOC-005 - bbox 기반 OCR field 파싱 파이프라인
    def _parse_extracted_meds_from_ocr_fields(
        self, ocr_fields: list[dict[str, str | float]]
    ) -> list[dict[str, str | float | None]]:
        if not ocr_fields:
            return []

        layout = self._segment_layout_regions(ocr_fields=ocr_fields)
        med_guide_fields = layout.get("med_guide_fields") or []
        summary_fields = layout.get("summary_fields") or []

        summary_lines = self._fields_to_lines(fields=summary_fields)
        if not summary_lines:
            summary_lines = self._fields_to_lines(fields=ocr_fields)

        summary_med_names = self._extract_summary_med_names(lines=summary_lines)
        summary_schedule_map = self._extract_summary_schedule_map(
            lines=summary_lines, summary_med_names=summary_med_names
        )
        dictionary_names = [name for name in summary_med_names if name]

        if med_guide_fields:
            med_guide_threshold = self._estimate_row_y_threshold(
                fields=med_guide_fields,
                factor=0.32,
                min_value=3.5,
                max_value=8.0,
            )
            med_guide_rows = self._group_fields_into_rows(fields=med_guide_fields, y_threshold=med_guide_threshold)
            med_guide_meds = self._parse_med_guide_table_rows(rows=med_guide_rows)
            med_guide_meds = self._post_validate_med_candidates(
                parsed_meds=med_guide_meds,
                dictionary_names=dictionary_names,
            )
            if med_guide_meds:
                self._merge_schedule_from_summary(parsed_meds=med_guide_meds, summary_schedule_map=summary_schedule_map)
                if config.OCR_ENABLE_SUMMARY_AUGMENT_FOR_MED_GUIDE:
                    return self._filter_parsed_meds_with_summary(
                        parsed_meds=med_guide_meds,
                        summary_med_names=summary_med_names,
                        summary_schedule_map=summary_schedule_map,
                    )
                return med_guide_meds

        summary_meds = self._parse_extracted_meds_with_regex(lines=summary_lines)
        summary_meds = self._post_validate_med_candidates(parsed_meds=summary_meds, dictionary_names=dictionary_names)
        if summary_meds:
            return summary_meds

        all_lines = self._fields_to_lines(fields=ocr_fields)
        return self._parse_extracted_meds_with_regex(lines=all_lines)

    # REQ-DOC-005 - OCR 레이아웃 분리(영수증/복약안내표/요약표)
    def _segment_layout_regions(  # noqa: C901
        self, ocr_fields: list[dict[str, str | float]]
    ) -> dict[str, list[dict[str, str | float]] | float | None]:
        rows = self._group_fields_into_rows(fields=ocr_fields)
        row_lines = [self._normalize_line(self._build_row_text(row_fields=row_fields)) for row_fields in rows]

        header_idx: int | None = None
        split_x: float | None = None
        for idx, row_fields in enumerate(rows):
            med_header = next((field for field in row_fields if "약품명" in str(field.get("text", ""))), None)
            guide_header = next((field for field in row_fields if "복약안내" in str(field.get("text", ""))), None)
            if med_header and guide_header:
                header_idx = idx
                split_x = (float(med_header.get("cx", 0.0)) + float(guide_header.get("cx", 0.0))) / 2
                break

        summary_idx: int | None = None
        if header_idx is not None:
            for idx in range(header_idx + 1, len(rows)):
                if self._is_summary_header_row_text(
                    current_line=row_lines[idx],
                    next_lines=row_lines[idx + 1 : idx + 6],
                ):
                    summary_idx = idx
                    break

        med_guide_fields: list[dict[str, str | float]] = []
        summary_fields: list[dict[str, str | float]] = []
        receipt_fields: list[dict[str, str | float]] = []

        if header_idx is None:
            return {
                "receipt_fields": receipt_fields,
                "med_guide_fields": med_guide_fields,
                "summary_fields": ocr_fields,
                "split_x": split_x,
            }

        header_row = rows[header_idx]
        header_top = min(float(field.get("y_min", 0.0)) for field in header_row) if header_row else 0.0
        summary_top = None
        if summary_idx is not None:
            summary_row = rows[summary_idx]
            summary_top = min(float(field.get("y_min", 0.0)) for field in summary_row) if summary_row else None

        for field in ocr_fields:
            y_min = float(field.get("y_min", 0.0))
            y_max = float(field.get("y_max", 0.0))
            cx = float(field.get("cx", 0.0))

            if y_max < header_top:
                if split_x is None or cx <= split_x:
                    receipt_fields.append(field)
                continue

            if summary_top is not None and y_min >= summary_top - 2:
                summary_fields.append(field)
                continue

            if y_min >= header_top - 2:
                med_guide_fields.append(field)

        if not summary_fields:
            summary_fields = [field for field in ocr_fields if field not in med_guide_fields]

        return {
            "receipt_fields": receipt_fields,
            "med_guide_fields": med_guide_fields,
            "summary_fields": summary_fields,
            "split_x": split_x,
        }

    # REQ-DOC-005 - field 영역을 row line 목록으로 변환
    def _fields_to_lines(self, fields: list[dict[str, str | float]], y_threshold: float | None = None) -> list[str]:
        rows = self._group_fields_into_rows(fields=fields, y_threshold=y_threshold)
        lines = [self._normalize_line(self._build_row_text(row_fields=row_fields)) for row_fields in rows]
        return [line for line in lines if line]

    # REQ-DOC-005 - summary 기반 스케줄값 보강
    def _merge_schedule_from_summary(
        self,
        *,
        parsed_meds: list[dict[str, str | float | None]],
        summary_schedule_map: dict[str, dict[str, str | None]],
    ) -> None:
        for med in parsed_meds:
            med_name = str(med.get("name") or "")
            if not med_name:
                continue
            schedule = self._find_schedule_from_summary(med_name=med_name, summary_schedule_map=summary_schedule_map)
            if not schedule:
                continue
            if schedule.get("dosage_text") and (
                not med.get("dosage_text")
                or re.search(r"(mg|g|mcg|ml)$", str(med.get("dosage_text") or ""), re.IGNORECASE)
            ):
                med["dosage_text"] = schedule["dosage_text"]
            if schedule.get("frequency_text") and not med.get("frequency_text"):
                med["frequency_text"] = schedule["frequency_text"]
            if schedule.get("duration_text") and not med.get("duration_text"):
                med["duration_text"] = schedule["duration_text"]

    # REQ-DOC-005 - 복약안내표 block parser
    def _parse_med_guide_table_rows(
        self, rows: list[list[dict[str, str | float]]]
    ) -> list[dict[str, str | float | None]]:
        header_idx: int | None = None
        split_x: float | None = None
        row_lines = [self._normalize_line(self._build_row_text(row_fields=row_fields)) for row_fields in rows]

        for idx, row_fields in enumerate(rows):
            med_header = next((field for field in row_fields if "약품명" in str(field.get("text", ""))), None)
            guide_header = next((field for field in row_fields if "복약안내" in str(field.get("text", ""))), None)
            if med_header and guide_header:
                header_idx = idx
                split_x = (float(med_header.get("cx", 0.0)) + float(guide_header.get("cx", 0.0))) / 2
                break

        if header_idx is None or split_x is None:
            return []

        blocks = self._build_medication_blocks(
            rows=rows[header_idx + 1 :],
            row_lines=row_lines[header_idx + 1 :],
            split_x=split_x,
        )
        parsed_meds: list[dict[str, str | float | None]] = []
        for block in blocks:
            med_item = self._build_med_from_block(block=block)
            if med_item:
                parsed_meds.append(med_item)
        return parsed_meds

    # REQ-DOC-005 - 새 약명 row를 기준으로 medication block 구성
    def _build_medication_blocks(
        self,
        *,
        rows: list[list[dict[str, str | float]]],
        row_lines: list[str],
        split_x: float,
    ) -> list[dict[str, list[str] | list[dict[str, str]]]]:
        blocks: list[dict[str, list[str] | list[dict[str, str]]]] = []
        current_block: dict[str, list[str] | list[dict[str, str]]] | None = None

        for idx, row_fields in enumerate(rows):
            row_text = (
                row_lines[idx]
                if idx < len(row_lines)
                else self._normalize_line(self._build_row_text(row_fields=row_fields))
            )
            if not row_text:
                continue
            if self._is_summary_header_row_text(current_line=row_text, next_lines=row_lines[idx + 1 : idx + 6]):
                break

            med_text = self._normalize_line(
                " ".join(
                    str(field.get("text", "")).strip()
                    for field in row_fields
                    if float(field.get("cx", 0.0)) <= split_x and str(field.get("text", "")).strip()
                )
            )
            guide_text = self._normalize_line(
                " ".join(
                    str(field.get("text", "")).strip()
                    for field in row_fields
                    if float(field.get("cx", 0.0)) > split_x and str(field.get("text", "")).strip()
                )
            )

            has_new_med = bool(med_text and self._looks_like_med_name_row(text=med_text))
            schedule = self._extract_schedule_from_text(text=guide_text or row_text)

            if has_new_med:
                current_block = {
                    "med_rows": [med_text],
                    "guide_rows": [guide_text] if guide_text else [],
                    "descriptor_rows": [],
                    "row_texts": [row_text],
                    "schedule_rows": [schedule] if schedule else [],
                }
                blocks.append(current_block)
                continue

            if current_block is None:
                continue

            row_texts = current_block["row_texts"]
            assert isinstance(row_texts, list)
            row_texts.append(row_text)

            if med_text:
                descriptor_rows = current_block["descriptor_rows"]
                assert isinstance(descriptor_rows, list)
                descriptor_rows.append(med_text)

            if guide_text:
                guide_rows = current_block["guide_rows"]
                assert isinstance(guide_rows, list)
                guide_rows.append(guide_text)

            if schedule:
                schedule_rows = current_block["schedule_rows"]
                assert isinstance(schedule_rows, list)
                schedule_rows.append(schedule)

        return blocks

    # REQ-DOC-005 - medication block -> ExtractedMed payload 변환
    def _build_med_from_block(
        self, block: dict[str, list[str] | list[dict[str, str]]]
    ) -> dict[str, str | float | None] | None:
        name_candidates = self._extract_med_name_candidates(block=block)
        if not name_candidates:
            return None

        med_name, strength_text = name_candidates[0]
        normalized_name = self._sanitize_extracted_med_name(name=med_name)
        if not self._is_valid_med_name(name=normalized_name):
            return None

        schedule_candidates = self._extract_schedule_candidates(block=block)
        schedule = schedule_candidates[0] if schedule_candidates else None

        med_item: dict[str, str | float | None] = {
            "name": normalized_name,
            "dosage_text": self._normalize_line(strength_text) if strength_text else None,
            "frequency_text": None,
            "duration_text": None,
            "confidence": 0.92 if schedule else 0.86,
        }
        if schedule:
            self._apply_schedule_to_med(med=med_item, schedule=schedule)
        return med_item

    # REQ-DOC-005 - block에서 약명 후보 추출
    def _extract_med_name_candidates(
        self, block: dict[str, list[str] | list[dict[str, str]]]
    ) -> list[tuple[str, str | None]]:
        candidates: list[tuple[str, str | None]] = []
        seen_keys: set[str] = set()
        med_rows = block.get("med_rows") or []
        for med_row in med_rows:
            candidate = self._extract_med_name_candidate_from_text(text=str(med_row))
            if not candidate:
                continue
            med_name, strength_text = candidate
            normalized_key = self._normalize_name_for_compare(name=med_name)
            if not normalized_key or normalized_key in seen_keys:
                continue
            seen_keys.add(normalized_key)
            candidates.append((med_name, strength_text))
        return candidates

    # REQ-DOC-005 - block에서 복약 스케줄 후보 추출
    def _extract_schedule_candidates(self, block: dict[str, list[str] | list[dict[str, str]]]) -> list[dict[str, str]]:
        schedule_candidates: list[dict[str, str]] = []
        seen_schedule_keys: set[tuple[str | None, str | None, str | None]] = set()

        raw_schedule_rows = block.get("schedule_rows") or []
        for schedule in raw_schedule_rows:
            if not isinstance(schedule, dict):
                continue
            schedule_key = (
                schedule.get("dosage_text"),
                schedule.get("frequency_text"),
                schedule.get("duration_text"),
            )
            if schedule_key in seen_schedule_keys:
                continue
            seen_schedule_keys.add(schedule_key)
            schedule_candidates.append(
                {
                    "dosage_text": str(schedule.get("dosage_text") or ""),
                    "frequency_text": str(schedule.get("frequency_text") or ""),
                    "duration_text": str(schedule.get("duration_text") or ""),
                }
            )

        guide_rows = block.get("guide_rows") or []
        row_texts = block.get("row_texts") or []
        for line in [*guide_rows, *row_texts]:
            schedule = self._extract_schedule_from_text(text=str(line))
            if not schedule:
                continue
            schedule_key = (
                schedule.get("dosage_text"),
                schedule.get("frequency_text"),
                schedule.get("duration_text"),
            )
            if schedule_key in seen_schedule_keys:
                continue
            seen_schedule_keys.add(schedule_key)
            schedule_candidates.append(schedule)
        return schedule_candidates

    # REQ-DOC-005 - dictionary 기반 후검증/정규화
    def _post_validate_med_candidates(
        self,
        *,
        parsed_meds: list[dict[str, str | float | None]],
        dictionary_names: list[str],
    ) -> list[dict[str, str | float | None]]:
        validated_meds: list[dict[str, str | float | None]] = []
        seen_keys: set[str] = set()

        for med in parsed_meds:
            med_name = str(med.get("name") or "").strip()
            if not med_name:
                continue
            normalized_name = self._normalize_name_with_dictionary(name=med_name, dictionary_names=dictionary_names)
            normalized_name = self._sanitize_extracted_med_name(name=normalized_name)
            if not self._is_valid_med_name(name=normalized_name):
                simple_candidate = self._extract_simple_med_name_from_text(text=normalized_name)
                if not simple_candidate:
                    continue
                normalized_name = simple_candidate[0]
            med_key = self._normalize_name_for_compare(name=normalized_name)
            if not med_key or med_key in seen_keys:
                continue
            seen_keys.add(med_key)

            validated_med = dict(med)
            validated_med["name"] = normalized_name
            validated_meds.append(validated_med)
        return validated_meds

    # REQ-DOC-005 - 약품명 dictionary 유사 매칭 정규화
    def _normalize_name_with_dictionary(self, *, name: str, dictionary_names: list[str]) -> str:
        if not dictionary_names:
            return name

        normalized_dict: dict[str, str] = {}
        for dictionary_name in dictionary_names:
            sanitized_name = self._sanitize_extracted_med_name(name=dictionary_name)
            if not self._is_valid_med_name(name=sanitized_name):
                continue
            dictionary_key = self._normalize_name_for_compare(name=sanitized_name)
            if dictionary_key and dictionary_key not in normalized_dict:
                normalized_dict[dictionary_key] = sanitized_name

        target_key = self._normalize_name_for_compare(name=name)
        if not target_key or not normalized_dict:
            return name
        if target_key in normalized_dict:
            return normalized_dict[target_key]

        for dictionary_key, dictionary_name in normalized_dict.items():
            if self._is_same_med_key(target_key, dictionary_key):
                return dictionary_name

        close_match_keys = get_close_matches(target_key, list(normalized_dict.keys()), n=1, cutoff=0.86)
        if close_match_keys:
            return normalized_dict[close_match_keys[0]]
        return name

    # REQ-DOC-005 - OCR field를 y축 기준 row로 그룹핑
    @staticmethod
    def _group_fields_into_rows(
        fields: list[dict[str, str | float]],
        y_threshold: float | None = None,
    ) -> list[list[dict[str, str | float]]]:
        valid_fields = [field for field in fields if str(field.get("text", "")).strip()]
        if not valid_fields:
            return []

        if y_threshold is None:
            y_threshold = OcrService._estimate_row_y_threshold(fields=valid_fields)

        ordered_fields = sorted(
            valid_fields,
            key=lambda field: (float(field.get("cy", 0.0)), float(field.get("x_min", 0.0))),
        )
        rows: list[dict[str, float | list[dict[str, str | float]]]] = []

        for field in ordered_fields:
            cy = float(field.get("cy", 0.0))
            target_row: dict[str, float | list[dict[str, str | float]]] | None = None
            for row in rows:
                row_cy = float(row["cy"])
                if abs(cy - row_cy) <= y_threshold:
                    target_row = row
                    break

            if target_row is None:
                rows.append({"cy": cy, "fields": [field]})
                continue

            row_fields = target_row["fields"]
            assert isinstance(row_fields, list)
            row_fields.append(field)
            target_row["cy"] = sum(float(item.get("cy", 0.0)) for item in row_fields) / max(len(row_fields), 1)

        grouped_rows: list[list[dict[str, str | float]]] = []
        for row in sorted(rows, key=lambda item: float(item["cy"])):
            row_fields = row["fields"]
            assert isinstance(row_fields, list)
            grouped_rows.append(sorted(row_fields, key=lambda item: float(item.get("x_min", 0.0))))
        return grouped_rows

    # REQ-DOC-005 - row grouping용 y threshold 계산
    @staticmethod
    def _estimate_row_y_threshold(
        fields: list[dict[str, str | float]],
        factor: float = 0.6,
        min_value: float = 8.0,
        max_value: float = 18.0,
    ) -> float:
        heights = [
            max(1.0, float(field.get("y_max", 0.0)) - float(field.get("y_min", 0.0)))
            for field in fields
            if str(field.get("text", "")).strip()
        ]
        if not heights:
            return min_value
        sorted_heights = sorted(heights)
        median_height = sorted_heights[len(sorted_heights) // 2]
        estimated = median_height * factor
        return max(min_value, min(max_value, estimated))

    # REQ-DOC-005 - row fields를 text line으로 결합
    @staticmethod
    def _build_row_text(row_fields: list[dict[str, str | float]]) -> str:
        texts = [str(field.get("text", "")).strip() for field in row_fields if str(field.get("text", "")).strip()]
        return " ".join(texts).strip()

    # REQ-DOC-005 - 처방 summary 헤더 패턴 감지
    @staticmethod
    def _has_prescription_summary_header(lines: list[str]) -> bool:
        for idx in range(len(lines)):
            window = " ".join(lines[idx : idx + 5])
            compact_window = re.sub(r"\s+", "", window)
            if (
                "처방의약품명" in compact_window
                and "1회투약량" in compact_window
                and "1일투여횟수" in compact_window
                and "총투약일수" in compact_window
            ):
                return True
        return False

    # REQ-DOC-005 - 복약안내표 영역 종료(요약표 시작) 탐지
    @staticmethod
    def _is_summary_header_row_text(current_line: str, next_lines: list[str]) -> bool:
        compact_current = re.sub(r"\s+", "", current_line)
        if (
            "처방의약품명" in compact_current
            or "1회투약량" in compact_current
            or "1일투여횟수" in compact_current
            or "총투약일수" in compact_current
        ):
            return True

        if "복약안내" in compact_current:
            return False

        if "약품명" in compact_current:
            compact_window = compact_current + "".join(re.sub(r"\s+", "", line) for line in next_lines[:4])
            has_dose = "투약량" in compact_window or "투여량" in compact_window or "1회투약량" in compact_window
            has_frequency = "횟수" in compact_window or "1일투여횟수" in compact_window
            has_duration = "일수" in compact_window or "총투약일수" in compact_window
            if has_dose and has_frequency and has_duration:
                return True
        return False

    # REQ-DOC-005 - 복약안내표 행이 약명 행인지 판별
    def _looks_like_med_name_row(self, text: str) -> bool:
        normalized_text = self._normalize_line(text)
        if not normalized_text:
            return False
        if self._is_descriptor_heavy_line(line=normalized_text):
            return False

        if not re.search(r"(정|캡슐|시럽|세립|과립|현탁액|액|주사|패치|패취)", normalized_text):
            return False

        med_candidate = self._extract_med_name_candidate_from_text(text=normalized_text)
        if not med_candidate:
            return False

        med_name, _ = med_candidate
        candidate_position = normalized_text.find(med_name)
        if candidate_position > 4:
            return False
        if len(normalized_text) >= len(med_name) + 10 and self._is_descriptor_heavy_line(line=normalized_text):
            return False
        return self._is_valid_med_name(name=self._sanitize_extracted_med_name(name=med_name))

    # REQ-DOC-005 - left column 텍스트에서 약명 후보 1개 추출
    def _extract_med_name_candidate_from_text(self, text: str) -> tuple[str, str | None] | None:  # noqa: C901
        normalized_text = self._normalize_line(text)
        if not normalized_text:
            return None
        if self._is_descriptor_heavy_line(line=normalized_text):
            return None

        med_base_pattern = re.compile(
            rf"([A-Za-z가-힣0-9+\-/]{{2,}}?(?:{MED_NAME_SUFFIX_PATTERN}))",
            re.IGNORECASE,
        )
        matched = med_base_pattern.search(normalized_text)
        if not matched:
            return None

        if matched.start() > 0:
            prefix_text = normalized_text[: matched.start()].strip()
            prefix_keywords = {"백색", "흰색", "미황색", "적갈색", "원형", "장방형", "분할선", "충전된", "과립이"}
            if any(keyword in prefix_text for keyword in prefix_keywords):
                return None

        candidate_text = matched.group(1).strip()
        trailing_text = normalized_text[matched.end() :]
        trailing_strength_match = re.match(
            r"^\s*(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|mL))",
            trailing_text,
            flags=re.IGNORECASE,
        )
        if trailing_strength_match:
            candidate_text = f"{candidate_text}{trailing_strength_match.group(1)}"
        candidate_text = re.split(r"[\(\[]", candidate_text)[0].strip()
        suffix_cut_match = re.match(
            rf"^(?P<base>.*?(?:{MED_NAME_SUFFIX_PATTERN}))(?P<strength>\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|mL))?",
            candidate_text,
            flags=re.IGNORECASE,
        )
        if suffix_cut_match:
            candidate_text = suffix_cut_match.group("base")
            suffix_strength = suffix_cut_match.group("strength")
            if suffix_strength:
                candidate_text = f"{candidate_text}{suffix_strength}"
        # 뒤에 붙는 stray single letter, 효능/설명성 토큰 제거
        candidate_text = re.sub(r"\s+[A-Za-z]$", "", candidate_text)
        med_name, strength_text = self._split_med_name_and_strength(text=candidate_text)
        if not med_name:
            return None
        if self._is_suspicious_generic_med_name(name=med_name):
            return None
        return med_name, strength_text

    # REQ-DOC-005 - 스케줄 값을 약 item에 병합
    @staticmethod
    def _apply_schedule_to_med(
        *,
        med: dict[str, str | float | None],
        schedule: dict[str, str],
    ) -> None:
        if schedule.get("dosage_text"):
            med["dosage_text"] = schedule["dosage_text"]
        if schedule.get("frequency_text"):
            med["frequency_text"] = schedule["frequency_text"]
        if schedule.get("duration_text"):
            med["duration_text"] = schedule["duration_text"]

    # REQ-DOC-005 - 약품명/강도 분리
    def _split_med_name_and_strength(self, text: str) -> tuple[str, str | None]:
        normalized_text = self._normalize_line(text)
        normalized_text = re.sub(r"\[(?:내복|외용|주사|경구|흡입)\]", "", normalized_text, flags=re.IGNORECASE)
        normalized_text = re.sub(r"\((?:내복|외용|주사|경구|흡입)\)", "", normalized_text, flags=re.IGNORECASE)
        normalized_text = re.sub(r"/(?:내복|외용|주사|경구|흡입)", "", normalized_text, flags=re.IGNORECASE)
        normalized_text = re.sub(
            r"/\d+(?:\.\d+)?\s*(?:정|캡슐|알|포|ml|mL|T|t)$", "", normalized_text, flags=re.IGNORECASE
        )
        normalized_text = normalized_text.strip().strip("/")
        if not normalized_text:
            return "", None

        med_form_suffix_pattern = "연질캡슐|장용캡슐|경질캡슐|필름코팅정|장용정|서방정|캡슐|정제|정|시럽|세립|과립|현탁액|액|주사액|주사|크림|로션|패취|패치"
        strength_pattern = r"(\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|mL))$"
        suffix_strength_match = re.search(
            rf"(?P<name>.*?(?:{med_form_suffix_pattern}))\s*(?P<strength>{strength_pattern})",
            normalized_text,
            flags=re.IGNORECASE,
        )
        if suffix_strength_match:
            med_name = suffix_strength_match.group("name").strip()
            strength_text = self._normalize_line(suffix_strength_match.group("strength"))
            return med_name, strength_text

        trailing_strength_match = re.search(strength_pattern, normalized_text, flags=re.IGNORECASE)
        if trailing_strength_match:
            strength_text = self._normalize_line(trailing_strength_match.group(1))
            med_name = normalized_text[: trailing_strength_match.start()].strip().strip("/")
            if med_name:
                return med_name, strength_text

        return normalized_text, None

    # REQ-DOC-005 - 복약안내 텍스트에서 용량/횟수/기간 추출
    def _extract_schedule_from_text(self, text: str) -> dict[str, str] | None:
        normalized_text = self._normalize_line(text)
        if not normalized_text:
            return None

        packed_match = PACKED_SCHEDULE_PATTERN.search(normalized_text)
        if packed_match:
            dose_count = packed_match.group(1).strip()
            dose_unit = (packed_match.group(2) or "").strip().lower()
            frequency_count = packed_match.group(3).strip()
            duration_days = packed_match.group(4).strip()
            dosage_text = self._build_dosage_text_from_count(
                med_name="",
                dose_count=dose_count,
                explicit_unit=dose_unit,
            )
            return {
                "dosage_text": dosage_text,
                "frequency_text": self._normalize_frequency_text(raw_text=f"{frequency_count}회")
                or f"{frequency_count}회",
                "duration_text": f"{duration_days}일분",
            }

        numeric_match = PACKED_NUMERIC_ROW_PATTERN.search(normalized_text)
        if numeric_match:
            dose_count = numeric_match.group("dose_count").strip()
            dose_unit = (numeric_match.group("dose_unit") or "").strip().lower()
            frequency_count = numeric_match.group("frequency_count").strip()
            duration_days = numeric_match.group("duration_days").strip()
            dosage_text = self._build_dosage_text_from_count(
                med_name="",
                dose_count=dose_count,
                explicit_unit=dose_unit,
            )
            return {
                "dosage_text": dosage_text,
                "frequency_text": self._normalize_frequency_text(raw_text=f"{frequency_count}회")
                or f"{frequency_count}회",
                "duration_text": f"{duration_days}일분",
            }

        return None

    # REQ-DOC-005 - 설명문 성격 라인 판별 강화
    @staticmethod
    def _is_descriptor_heavy_line(line: str) -> bool:
        normalized_line = line.strip()
        if not normalized_line:
            return False

        strong_descriptor_keywords = {
            "백색",
            "흰색",
            "미황색",
            "적갈색",
            "원형",
            "장방형",
            "분할선",
            "정제",
            "과립이",
            "충전된",
            "소화관",
            "제산제",
            "소화제",
            "진경제",
            "수면진정제",
            "항우울제",
            "불면증",
            "위식도",
            "완화",
            "예방",
            "치료제",
            "증상",
            "약입니다",
            "완화시켜",
            "배출되도록",
        }
        matched_count = sum(1 for keyword in strong_descriptor_keywords if keyword in normalized_line)
        has_med_suffix = bool(re.search(r"(정|캡슐|시럽|세립|과립|현탁액|주사|액|패치|패취)", normalized_line))
        if matched_count >= 2 and not has_med_suffix:
            return True
        if matched_count >= 1 and len(normalized_line) >= 18 and not has_med_suffix:
            return True

        if "정제" in normalized_line and (
            "백색" in normalized_line or "흰색" in normalized_line or "장방형" in normalized_line
        ):
            return True
        return False

    # REQ-DOC-005 - OCR 용량값과 summary 용량값 우선순위 정리
    @staticmethod
    def _resolve_dosage_text_for_output(
        dosage_text: str | None,
        packed_dosage_text: str | None,
        schedule_from_summary: dict[str, str | None] | None,
    ) -> str | None:
        summary_dosage_text = schedule_from_summary["dosage_text"] if schedule_from_summary else None
        candidate_dosage_text = dosage_text or packed_dosage_text or summary_dosage_text
        if not candidate_dosage_text:
            return None

        if summary_dosage_text and dosage_text:
            compact_dosage_text = dosage_text.replace(" ", "").lower()
            has_count_unit = bool(re.search(r"(정|캡슐|알|포|t)$", compact_dosage_text))
            is_strength_only = bool(re.search(r"(mg|g|mcg|ml)$", compact_dosage_text))
            if is_strength_only and not has_count_unit:
                return summary_dosage_text

        compact_candidate = re.sub(r"\s+", "", candidate_dosage_text)
        count_unit_match = re.fullmatch(r"(\d+(?:\.\d+)?)(정|캡슐|알|포|ml|mL|T|t)", compact_candidate)
        if count_unit_match:
            dose_count = count_unit_match.group(1)
            unit = count_unit_match.group(2)
            normalized_unit = "정" if unit.lower() == "t" else unit
            return f"{dose_count}{normalized_unit}씩"
        return candidate_dosage_text

    # REQ-DOC-005 - 하단 약품명/투약량/횟수/일수 표에서 복약 스케줄 추출
    def _extract_summary_schedule_map(
        self, lines: list[str], summary_med_names: list[str]
    ) -> dict[str, dict[str, str | None]]:
        summary_header_idx = self._find_summary_header_index(lines=lines)
        if summary_header_idx is None:
            return {}

        schedule_map: dict[str, dict[str, str | None]] = {}
        summary_lines = lines[summary_header_idx + 1 :]

        idx = 0
        while idx < len(summary_lines):
            current_line = summary_lines[idx].strip()
            if "본인의 약은" in current_line or "처방조제된 약은" in current_line:
                break

            inline_row = self._parse_inline_summary_row(line=current_line)
            if inline_row:
                med_name = inline_row["med_name"]
                med_key = self._normalize_name_for_compare(name=med_name)
                if med_key:
                    schedule_map[med_key] = {
                        "dosage_text": self._build_dosage_text_from_count(
                            med_name=med_name, dose_count=inline_row["dose_count"]
                        ),
                        "frequency_text": self._normalize_frequency_text(raw_text=f"{inline_row['frequency_count']}회"),
                        "duration_text": f"{inline_row['duration_days']}일분",
                    }
                idx += 1
                continue

            is_med_line = self._is_possible_summary_med_line(
                current_line
            ) or self._is_possible_summary_name_from_numeric_row(
                line=current_line, next_lines=summary_lines[idx + 1 : idx + 5]
            )
            if not is_med_line:
                idx += 1
                continue

            med_name = self._sanitize_extracted_med_name(name=current_line.lstrip("+").strip())
            med_name = re.sub(r"(?<=\d)m$", "mg", med_name, flags=re.IGNORECASE)
            med_key = self._normalize_name_for_compare(name=med_name)
            if not med_key:
                idx += 1
                continue

            numeric_values, cursor = self._extract_numeric_values_after_line(
                summary_lines=summary_lines, start_idx=idx + 1
            )

            if len(numeric_values) >= 3:
                dose_count = numeric_values[0]
                frequency_count = numeric_values[1]
                duration_days = numeric_values[2]
                schedule_map[med_key] = {
                    "dosage_text": self._build_dosage_text_from_count(med_name=med_name, dose_count=dose_count),
                    "frequency_text": self._normalize_frequency_text(raw_text=f"{frequency_count}회"),
                    "duration_text": f"{duration_days}일분",
                }
                idx = cursor
                continue

            idx += 1

        return schedule_map

    # REQ-DOC-005 - summary 표 헤더 인덱스 탐색
    @staticmethod
    def _find_summary_header_index(lines: list[str]) -> int | None:
        for idx in range(len(lines)):
            window = " ".join(lines[idx : idx + 8])
            compact_window = re.sub(r"\s+", "", window)
            has_med_name = "약품명" in window or "처방의약품명" in compact_window
            has_dose = "투약량" in window or "투여량" in window or "1회투약량" in compact_window
            has_frequency = "횟수" in window or "1일투여횟수" in compact_window
            has_duration = "일수" in window or "총투약일수" in compact_window
            if has_med_name and has_dose and has_frequency and has_duration:
                return idx
        return None

    # REQ-DOC-005 - summary 표 숫자열 추출
    @staticmethod
    def _extract_numeric_values_after_line(summary_lines: list[str], start_idx: int) -> tuple[list[str], int]:
        numeric_values: list[str] = []
        cursor = start_idx
        while cursor < len(summary_lines) and len(numeric_values) < 4:
            value_line = summary_lines[cursor].strip()
            direct_numeric_match = re.fullmatch(r"\d+", value_line)
            if direct_numeric_match:
                numeric_values.append(direct_numeric_match.group(0))
                cursor += 1
                continue

            numeric_with_unit_match = re.fullmatch(r"(\d+)\s*(?:정|캡슐|알|포|회|일분|일)", value_line)
            if numeric_with_unit_match:
                numeric_values.append(numeric_with_unit_match.group(1))
                cursor += 1
                continue
            break
        return numeric_values, cursor

    # REQ-DOC-005 - OCR 텍스트에서 복약 표 영역만 우선 추출
    @staticmethod
    def _extract_medication_section_lines(lines: list[str]) -> list[str]:
        if not lines:
            return lines

        section_start_idx: int | None = None
        for idx in range(len(lines)):
            window = " ".join(lines[idx : idx + 8])
            if "약품사진" in window and "약품명" in window and "복약안내" in window:
                section_start_idx = idx
                break
        if section_start_idx is None:
            for idx in range(len(lines)):
                window = " ".join(lines[idx : idx + 8])
                if "약품명" in window and "복약안내" in window:
                    section_start_idx = idx
                    break

        if section_start_idx is None:
            return lines

        section_end_idx = len(lines)
        for idx in range(section_start_idx + 12, len(lines)):
            window = " ".join(lines[idx : idx + 8])
            has_med_name = "약품명" in window
            has_dose = "투약량" in window or "투여량" in window
            has_frequency = "횟수" in window
            has_duration = "일수" in window
            if has_med_name and has_dose and has_frequency and has_duration:
                section_end_idx = idx
                break

        return lines[section_start_idx:section_end_idx]

    # REQ-DOC-005 - 하단 약품명/투약량 표에서 약명 후보 추출
    def _extract_summary_med_names(self, lines: list[str]) -> list[str]:
        summary_header_idx = self._find_summary_header_index(lines=lines)
        if summary_header_idx is None:
            return []

        summary_names: list[str] = []
        seen_keys: set[str] = set()
        summary_lines = lines[summary_header_idx + 1 :]
        for idx, line in enumerate(summary_lines):
            if "본인의 약은" in line or "처방조제된 약은" in line:
                break
            inline_row = self._parse_inline_summary_row(line=line)
            if inline_row:
                normalized_name = inline_row["med_name"]
            else:
                is_summary_med_line = self._is_possible_summary_med_line(line=line)
                if not is_summary_med_line:
                    is_summary_med_line = self._is_possible_summary_name_from_numeric_row(
                        line=line, next_lines=summary_lines[idx + 1 : idx + 5]
                    )
                if not is_summary_med_line:
                    continue

                normalized_name = self._sanitize_extracted_med_name(name=line.lstrip("+").strip())
            normalized_name = re.sub(r"(?<=\d)m$", "mg", normalized_name, flags=re.IGNORECASE)
            if not self._is_valid_med_name(name=normalized_name):
                continue

            compare_key = self._normalize_name_for_compare(name=normalized_name)
            if not compare_key or compare_key in seen_keys:
                continue
            seen_keys.add(compare_key)
            summary_names.append(normalized_name)

        return summary_names

    # REQ-DOC-005 - summary 표 약명 후보 라인 판별
    @staticmethod
    def _is_possible_summary_med_line(line: str) -> bool:  # noqa: C901
        candidate = line.strip()
        if not candidate:
            return False
        if candidate in {"약품명", "투약량", "투여량", "횟수", "일수", "총투"}:
            return False
        if re.fullmatch(r"[0-9\s,./()\-+:℃%]+", candidate):
            return False
        if len(candidate) > 30 or len(candidate) < 4:
            return False
        if not re.search(r"[A-Za-z가-힣]", candidate):
            return False
        tokens = candidate.split()
        if len(tokens) >= 3:
            return False
        if len(tokens) == 2:
            is_strength_token = bool(
                re.fullmatch(
                    r"\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?(?:mg|g|mcg|ml|mL)?",
                    tokens[1],
                    re.IGNORECASE,
                )
            )
            if not is_strength_token:
                return False
        if "1정씩" in candidate or "1캡슐" in candidate or "1포씩" in candidate:
            return False
        if any(keyword in candidate for keyword in MED_DESCRIPTOR_KEYWORDS):
            return False
        if any(
            keyword in candidate
            for keyword in {"주의", "보관", "복용", "용량", "치료제", "입니다", "요법", "안지오텐신", "수용체"}
        ):
            return False
        has_med_suffix = bool(re.search(r"(캡슐|정|정제|시럽|세립|과립|현탁액|주사|크림|로션|패치|패취)$", candidate))
        has_dose_pattern = bool(re.search(r"\d+(?:\.\d+)?/\d+(?:\.\d+)?m?g?$", candidate, flags=re.IGNORECASE))
        has_suffix_strength_pattern = bool(
            re.search(
                rf"(?:{MED_NAME_SUFFIX_PATTERN})\s*\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?\s*(?:mg|g|mcg|ml|mL)$",
                candidate,
                flags=re.IGNORECASE,
            )
        )
        has_extended_name = bool(re.search(r"\d+시간이알$", candidate))
        if not (has_med_suffix or has_dose_pattern or has_suffix_strength_pattern or has_extended_name):
            return False
        return True

    # REQ-DOC-005 - suffix 누락 약명의 숫자열 행 패턴 보정
    @staticmethod
    def _is_possible_summary_name_from_numeric_row(line: str, next_lines: list[str]) -> bool:
        candidate = line.strip().replace("+", "")
        if not candidate or " " in candidate:
            return False
        if len(candidate) < 6:
            return False
        if not re.search(r"[A-Za-z가-힣]", candidate):
            return False
        if any(keyword in candidate for keyword in MED_DESCRIPTOR_KEYWORDS):
            return False
        if any(keyword in candidate for keyword in {"주의", "보관", "복용", "용량", "치료제", "입니다"}):
            return False

        numeric_count = 0
        for next_line in next_lines:
            if re.fullmatch(r"\d+", next_line.strip()):
                numeric_count += 1
            else:
                break
        return numeric_count >= 3

    # REQ-DOC-005 - summary 기반 오탐 필터링 + 누락 약명 보정
    def _filter_parsed_meds_with_summary(
        self,
        parsed_meds: list[dict[str, str | float | None]],
        summary_med_names: list[str],
        summary_schedule_map: dict[str, dict[str, str | None]],
    ) -> list[dict[str, str | float | None]]:
        summary_keys = [self._normalize_name_for_compare(name=name) for name in summary_med_names]
        summary_keys = [key for key in summary_keys if key]
        if not summary_keys:
            return parsed_meds

        filtered_meds: list[dict[str, str | float | None]] = []
        for parsed_med in parsed_meds:
            med_name = str(parsed_med.get("name") or "")
            med_key = self._normalize_name_for_compare(name=med_name)
            if not med_key:
                continue

            filtered_meds.append(parsed_med)
            # summary 표에 없는 약명도 유지한다.
            # OCR이 일부 약명을 누락해도 복약표 영역에서 잡힌 약은 결과에 남겨야 한다.

        existing_keys = {
            existing_key
            for existing_key in (
                self._normalize_name_for_compare(name=str(med.get("name") or "")) for med in filtered_meds
            )
            if existing_key
        }
        for summary_name in summary_med_names:
            summary_key = self._normalize_name_for_compare(name=summary_name)
            if not summary_key:
                continue
            if summary_key in existing_keys:
                continue
            schedule = summary_schedule_map.get(summary_key)
            filtered_meds.append(
                {
                    "name": summary_name,
                    "dosage_text": schedule["dosage_text"] if schedule else None,
                    "frequency_text": schedule["frequency_text"] if schedule else None,
                    "duration_text": schedule["duration_text"] if schedule else None,
                    "confidence": 0.70,
                }
            )
            existing_keys.add(summary_key)

        return filtered_meds or parsed_meds

    # REQ-DOC-005 - 약명 비교용 키 정규화
    def _normalize_name_for_compare(self, name: str) -> str:
        normalized_name = self._normalize_med_name(name=name)
        normalized_name = re.sub(r"(?<=\d)m$", "mg", normalized_name, flags=re.IGNORECASE)
        normalized_name = re.sub(r"\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|mL)$", "", normalized_name, flags=re.IGNORECASE)
        normalized_name = re.sub(
            r"\d+(?:\.\d+)?/\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|mL)?$",
            "",
            normalized_name,
            flags=re.IGNORECASE,
        )
        normalized_name = re.sub(r"[^A-Za-z가-힣0-9]", "", normalized_name)
        return normalized_name.casefold().strip()

    # REQ-DOC-005 - summary 기반 스케줄 매핑 조회
    def _find_schedule_from_summary(
        self, med_name: str, summary_schedule_map: dict[str, dict[str, str | None]]
    ) -> dict[str, str | None] | None:
        med_key = self._normalize_name_for_compare(name=med_name)
        if not med_key:
            return None
        direct_schedule = summary_schedule_map.get(med_key)
        if direct_schedule:
            return direct_schedule
        for summary_key, schedule in summary_schedule_map.items():
            if self._is_same_med_key(med_key, summary_key):
                return schedule
        return None

    # REQ-DOC-005 - 투약량 숫자를 약 형태에 맞춰 문자열로 변환
    @staticmethod
    def _build_dosage_text_from_count(med_name: str, dose_count: str, explicit_unit: str = "") -> str:
        normalized_unit = explicit_unit.lower()
        if normalized_unit in {"정", "capsule", "캡슐", "알", "포", "ml"}:
            unit_text = "캡슐" if normalized_unit == "capsule" else normalized_unit
            return f"{dose_count}{unit_text}씩"

        normalized_name = med_name.replace(" ", "")
        if "시럽" in normalized_name:
            return f"{dose_count}포씩"
        if "캡슐" in normalized_name:
            return f"{dose_count}캡슐씩"
        return f"{dose_count}정씩"

    # REQ-DOC-005 - 약명 키 유사도 비교
    @staticmethod
    def _is_same_med_key(left_key: str, right_key: str) -> bool:
        if not left_key or not right_key:
            return False
        if left_key == right_key:
            return True
        min_len = min(len(left_key), len(right_key))
        if min_len < 4:
            return False
        return left_key in right_key or right_key in left_key

    # REQ-DOC-005 - OCR 파싱 노이즈 라인 제외
    @staticmethod
    def _is_noise_line(line: str) -> bool:
        lowered_line = line.casefold()
        if any(keyword in lowered_line for keyword in NOISE_KEYWORDS):
            return True
        if re.fullmatch(r"[0-9\s,./()\-+:℃%]+", line):
            return True
        return len(re.sub(r"\s+", "", line)) <= 1

    # REQ-DOC-005 - OCR 라인 정규화
    @staticmethod
    def _normalize_line(line: str) -> str:
        normalized_line = line.replace("\u200b", " ").strip()
        normalized_line = normalized_line.replace("캅셀", "캡슐").replace("캡셀", "캡슐").replace("캅슐", "캡슐")
        normalized_line = re.sub(r"(?<=\d)m(?=\s|$)", "mg", normalized_line, flags=re.IGNORECASE)
        normalized_line = re.sub(r"(서방정|장용캡슐|연질캡슐|캡슐|정)(?=\d)", r"\1 ", normalized_line)
        return re.sub(r"\s+", " ", normalized_line)

    # REQ-DOC-005 - 약명 정규화
    @staticmethod
    def _normalize_med_name(name: str) -> str:
        cleaned_name = re.sub(r"[^A-Za-z가-힣0-9+\-/ ]", "", name)
        cleaned_name = re.sub(r"\s+", " ", cleaned_name).strip()
        cleaned_name = cleaned_name.replace("캅셀", "캡슐").replace("캡셀", "캡슐").replace("캅슐", "캡슐")
        cleaned_name = re.sub(r"(?<=\d)m$", "mg", cleaned_name, flags=re.IGNORECASE)
        corrected_name = MED_NAME_OCR_CORRECTIONS.get(cleaned_name)
        if corrected_name:
            return corrected_name
        return cleaned_name

    # REQ-DOC-005 - 일반 제형 단어 오탐 제외
    @staticmethod
    def _is_valid_med_name(name: str) -> bool:  # noqa: C901
        if not name:
            return False
        normalized = name.strip()
        if not normalized:
            return False
        compact_name = re.sub(r"\s+", "", normalized).replace("+", "")
        if OcrService._contains_non_med_keyword(compact_name=compact_name):
            return False
        if OcrService._is_suspicious_generic_med_name(name=compact_name):
            return False
        base_name = re.sub(
            r"(연질캡슐|장용캡슐|경질캡슐|필름코팅정|장용정|서방정|캡슐|정제|정|시럽|세립|과립|현탁액|주사액|주사|크림|로션|패치|패취)$",
            "",
            compact_name,
        )
        if not re.search(r"[A-Za-z가-힣]", base_name):
            return False
        if compact_name in GENERIC_MED_NAMES:
            return False
        if len(compact_name) <= 3 and compact_name.endswith("정"):
            return False
        if OcrService._looks_like_descriptor_noise(compact_name=compact_name):
            return False
        if len(compact_name) < 3:
            return False
        if compact_name.endswith(("해주", "시켜주", "와주는", "배출되도록")):
            return False
        return True

    # REQ-DOC-005 - 비약품 키워드 포함 여부 검사
    @staticmethod
    def _contains_non_med_keyword(compact_name: str) -> bool:
        return any(keyword in compact_name for keyword in NON_MED_NAME_KEYWORDS)

    # REQ-DOC-005 - 일반 descriptor + 제형 조합 오탐 제외
    @staticmethod
    def _is_suspicious_generic_med_name(name: str) -> bool:
        compact_name = re.sub(r"\s+", "", name)
        if not compact_name:
            return True

        generic_descriptor_pattern = r"(?:장용성|서방성|연질|경질|필름코팅)+"
        generic_form_pattern = r"(?:정|정제|캡슐|과립|세립|시럽|현탁액|액|주사|패치|패취)"
        if re.fullmatch(rf"{generic_descriptor_pattern}{generic_form_pattern}", compact_name):
            return True

        if compact_name in {"장용성과립", "서방성정", "연질캡슐", "경질캡슐", "필름코팅정"}:
            return True
        return False

    # REQ-DOC-005 - 설명문/제형 묘사 문구 오탐 검사
    @staticmethod
    def _looks_like_descriptor_noise(compact_name: str) -> bool:
        if not any(keyword in compact_name for keyword in MED_DESCRIPTOR_KEYWORDS):
            return False
        if compact_name.endswith(("정", "정제", "캡슐", "시럽", "세립", "과립")) and len(compact_name) <= 10:
            return True
        return any(keyword in compact_name for keyword in {"완화시켜", "배출되도록", "약입니다", "분말", "원형"})

    # REQ-DOC-005 - 최종 추출약 유효성(스케줄 정보/약명 길이) 판별
    @staticmethod
    def _is_useful_parsed_med(parsed_med: dict[str, str | float | None]) -> bool:
        med_name = str(parsed_med.get("name") or "").strip()
        if not med_name:
            return False

        has_schedule = any(
            parsed_med.get(field_name) for field_name in ("dosage_text", "frequency_text", "duration_text")
        )
        if has_schedule:
            return True

        compact_name = re.sub(r"\s+", "", med_name)
        if len(compact_name) >= 4:
            return True
        if compact_name.endswith(("정", "캡슐", "시럽", "세립", "과립", "현탁액", "주사", "패치", "패취")):
            return True
        return False

    # REQ-DOC-005 - 정규식 첫 매치 추출
    @staticmethod
    def _extract_first(line: str, pattern: re.Pattern[str]) -> str | None:
        match = pattern.search(line)
        if not match:
            return None
        return match.group(1).strip()

    # REQ-DOC-005 - 약봉투형 OCR의 분리 컬럼(약명/복약안내) 매핑 보정
    def _apply_packed_schedule_fallback(  # noqa: C901
        self,
        *,
        parsed_meds: list[dict[str, str | float | None]],
        lines: list[str],
    ) -> None:
        if not parsed_meds:
            return

        packed_schedules = self._extract_packed_schedules(lines=lines)
        if not packed_schedules:
            return

        if len(packed_schedules) >= len(parsed_meds):
            for med, schedule in zip(parsed_meds, packed_schedules, strict=False):
                if schedule.get("dosage_text"):
                    med["dosage_text"] = schedule["dosage_text"]
                if schedule.get("frequency_text"):
                    med["frequency_text"] = schedule["frequency_text"]
                if schedule.get("duration_text"):
                    med["duration_text"] = schedule["duration_text"]
            return

        schedule_idx = 0
        for med in parsed_meds:
            if schedule_idx >= len(packed_schedules):
                break
            if med.get("frequency_text") and med.get("duration_text"):
                continue
            schedule = packed_schedules[schedule_idx]
            schedule_idx += 1
            if not med.get("dosage_text") and schedule.get("dosage_text"):
                med["dosage_text"] = schedule["dosage_text"]
            if not med.get("frequency_text") and schedule.get("frequency_text"):
                med["frequency_text"] = schedule["frequency_text"]
            if not med.get("duration_text") and schedule.get("duration_text"):
                med["duration_text"] = schedule["duration_text"]

    # REQ-DOC-005 - 텍스트 전체에서 "N정씩 M회 D일분" 패턴 목록 추출
    def _extract_packed_schedules(self, lines: list[str]) -> list[dict[str, str]]:
        schedules: list[dict[str, str]] = []
        for line in lines:
            normalized_line = self._normalize_line(line)
            packed_match = PACKED_SCHEDULE_PATTERN.search(normalized_line)
            if packed_match:
                dose_count = packed_match.group(1).strip()
                dose_unit = (packed_match.group(2) or "").strip().lower()
                frequency_count = packed_match.group(3).strip()
                duration_days = packed_match.group(4).strip()
            else:
                numeric_row_match = PACKED_NUMERIC_ROW_PATTERN.match(normalized_line)
                if not numeric_row_match:
                    continue
                dose_count = numeric_row_match.group("dose_count").strip()
                dose_unit = (numeric_row_match.group("dose_unit") or "").strip().lower()
                frequency_count = numeric_row_match.group("frequency_count").strip()
                duration_days = numeric_row_match.group("duration_days").strip()
            schedules.append(
                {
                    "dosage_text": self._build_dosage_text_from_count(
                        med_name="",
                        dose_count=dose_count,
                        explicit_unit=dose_unit,
                    ),
                    "frequency_text": self._normalize_frequency_text(raw_text=f"{frequency_count}회"),
                    "duration_text": f"{duration_days}일분",
                }
            )
        return schedules

    # REQ-DOC-005 - 문맥 라인에서 1일 횟수 텍스트 추출/정규화
    def _extract_frequency_text_from_context(self, context_line: str) -> str | None:
        summary_match = SUMMARY_FREQUENCY_LABEL_PATTERN.search(context_line)
        if summary_match:
            return self._normalize_frequency_text(raw_text=f"{summary_match.group(1).strip()}회")
        raw_frequency_text = self._extract_first(line=context_line, pattern=FREQUENCY_PATTERN)
        return self._normalize_frequency_text(raw_text=raw_frequency_text)

    # REQ-DOC-005 - 문맥 라인에서 기간(일) 텍스트 추출/정규화
    def _extract_duration_text_from_context(self, context_line: str) -> str | None:
        summary_match = SUMMARY_DURATION_LABEL_PATTERN.search(context_line)
        if summary_match:
            return f"{summary_match.group(1).strip()}일분"
        duration_text = self._extract_first(line=context_line, pattern=DURATION_PATTERN)
        if not duration_text:
            return None
        normalized_day_match = re.search(r"(\d+)\s*(?:일분|일)", duration_text)
        if normalized_day_match:
            return f"{normalized_day_match.group(1)}일분"
        return duration_text

    # REQ-DOC-005 - 요약 표(코드+약명+수치 한 줄) 파싱
    def _parse_inline_summary_row(self, line: str) -> dict[str, str] | None:
        candidate = line.strip()
        if not candidate:
            return None
        if "약품명" in candidate and ("횟수" in candidate or "일수" in candidate):
            return None

        compact_candidate = re.sub(r"\s+", " ", candidate)
        compact_candidate = re.sub(r"^\+?\d{6,}\s+", "", compact_candidate).strip()
        matched = re.match(
            r"^(?P<med_name>.+?)\s+"
            r"(?P<dose_count>\d+(?:\.\d+)?)(?:\s*(?:정|캡슐|알|포|ml|mL))?\s+"
            r"(?P<frequency_count>\d+)(?:\s*회)?\s+"
            r"(?P<duration_days>\d+)(?:\s*(?:일|일분))?(?:\s+\d+)?(?:\s+.*)?$",
            compact_candidate,
            flags=re.IGNORECASE,
        )
        if not matched:
            return None

        med_name = self._sanitize_extracted_med_name(name=matched.group("med_name"))
        if not self._is_valid_med_name(name=med_name):
            return None

        return {
            "med_name": med_name,
            "dose_count": matched.group("dose_count"),
            "frequency_count": matched.group("frequency_count"),
            "duration_days": matched.group("duration_days"),
        }

    # REQ-DOC-005 - 약명 후보 문자열 정리(내복/1정 꼬리 제거)
    def _sanitize_extracted_med_name(self, name: str) -> str:
        cleaned_name = self._normalize_med_name(name=name)
        cleaned_name = re.sub(r"\[(?:내복|외용|주사|경구|흡입)\]", "", cleaned_name, flags=re.IGNORECASE)
        cleaned_name = re.sub(r"\((?:내복|외용|주사|경구|흡입)\)", "", cleaned_name, flags=re.IGNORECASE)
        cleaned_name = re.sub(r"/(?:내복|외용|주사|경구|흡입)", "", cleaned_name, flags=re.IGNORECASE)
        cleaned_name = re.sub(
            r"/\d+(?:\.\d+)?\s*(?:정|캡슐|알|포|ml|mL|T|t)(?:씩)?$",
            "",
            cleaned_name,
            flags=re.IGNORECASE,
        )
        cleaned_name = re.sub(
            rf"({MED_NAME_SUFFIX_PATTERN})\s*\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?(?:\s*(?:mg|g|mcg|ml|mL))?$",
            r"\1",
            cleaned_name,
            flags=re.IGNORECASE,
        )
        cleaned_name = re.sub(r"\s*\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|mL)$", "", cleaned_name, flags=re.IGNORECASE)
        cleaned_name = re.sub(r"/{2,}", "/", cleaned_name)
        cleaned_name = cleaned_name.strip().strip("/")
        return re.sub(r"\s+", " ", cleaned_name).strip()

    # REQ-DOC-005 - 횟수 텍스트 정규화
    @staticmethod
    def _normalize_frequency_text(raw_text: str | None) -> str | None:
        if raw_text is None:
            return None

        stripped_text = raw_text.strip()
        if not stripped_text:
            return None

        compact_text = re.sub(r"\s+", "", stripped_text).lower()
        if "필요시" in compact_text or "prn" in compact_text:
            return "필요 시"

        frequency_count_match = re.search(r"(\d+)\s*회", stripped_text)
        if frequency_count_match:
            return f"{frequency_count_match.group(1)}회"

        parts: list[str] = []
        if "아침" in compact_text:
            parts.append("아침")
        if "점심" in compact_text:
            parts.append("점심")
        if "저녁" in compact_text:
            parts.append("저녁")
        if "취침전" in compact_text:
            parts.append("취침 전")
        if parts:
            return "/".join(parts)

        return stripped_text

    # REQ-DOC-001, REQ-DOC-002, REQ-DOC-008 - 문서 접근 권한 확인
    async def _has_patient_access(self, user: User, patient_id: int) -> bool:
        own_patient = await Patient.get_or_none(user_id=user.id)
        if own_patient and own_patient.id == patient_id:
            return True
        return await CaregiverPatientLink.filter(
            caregiver_user_id=user.id,
            patient_id=patient_id,
            status="active",
            revoked_at__isnull=True,
        ).exists()

    # REQ-DOC-008 - OCR 실패 코드 매핑
    @staticmethod
    def _build_error_code(exc: Exception) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return "OCR_TIMEOUT"
        if isinstance(exc, httpx.HTTPError):
            return "OCR_HTTP_ERROR"
        if str(exc).startswith("NAVER_OCR_HTTP_"):
            return "OCR_HTTP_ERROR"
        return "OCR_FAILED"
