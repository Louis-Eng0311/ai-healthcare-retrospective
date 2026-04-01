from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.dtos.base import BaseSerializerModel

DocumentStatus = Literal["uploaded", "deleted"]
OcrStatus = Literal["queued", "processing", "success", "failed"]


# 문서 목록 조회 필터 - REQ-DOC-002
class DocumentListQuery(BaseModel):
    patient_id: Annotated[int | None, Field(default=None, ge=1)]
    date_from: date | None = None
    date_to: date | None = None
    document_status: DocumentStatus | None = None
    ocr_status: OcrStatus | None = None


# 대상 patient 귀속 + 업로드/OCR 상태 응답 - REQ-USER-008, REQ-DOC-003
class DocumentUploadResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    uploaded_by_user_id: int
    status: DocumentStatus
    created_at: datetime


# 문서 목록 조회 응답 - REQ-DOC-002
class DocumentListItemResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    uploaded_by_user_id: int
    original_filename: str | None
    file_type: str | None
    file_size: int | None
    status: DocumentStatus
    ocr_status: OcrStatus | None
    has_confirmed_meds: bool = False
    created_at: datetime


class DocumentListResponse(BaseSerializerModel):
    items: list[DocumentListItemResponse]
    total: int


# 문서 soft delete 응답 - REQ-DOC-001
class DocumentDeleteResponse(BaseSerializerModel):
    document_id: int
    status: Literal["deleted"]
    deleted_at: datetime


# 문서명 변경 요청 - REQ-DOC-002
class DocumentRenameRequest(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=255)]


# 문서명 변경 응답 - REQ-DOC-002
class DocumentRenameResponse(BaseSerializerModel):
    document_id: int
    original_filename: str


# OCR 처리 상태 조회 응답 - REQ-DOC-003
class DocumentOcrStatusResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    document_status: DocumentStatus
    has_confirmed_meds: bool = False
    ocr_job_id: int | None
    ocr_status: OcrStatus | None
    retry_count: int | None
    error_code: str | None
    error_message: str | None
    barcode_detected: bool = False
    barcode_count: int = 0
    barcode_values: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None


# OCR 결과 원문 조회 응답 - REQ-DOC-003
class DocumentOcrTextResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    ocr_job_id: int | None
    ocr_status: OcrStatus | None
    raw_text: str | None
    created_at: datetime


# OCR 재시도 요청 응답 - REQ-DOC-008
class DocumentOcrRetryResponse(BaseSerializerModel):
    document_id: int
    ocr_job_id: int
    status: Literal["queued"]
    retry_count: int
    queued_at: datetime


# 추출 약 식약처 정보 응답 - REQ-DRUG-001, REQ-DRUG-002, REQ-DRUG-003
class ExtractedDrugMfdsInfoResponse(BaseSerializerModel):
    drug_info_cache_id: int
    mfds_item_seq: str | None
    drug_name_display: str | None
    manufacturer: str | None
    efficacy: str | None
    dosage_info: str | None
    precautions: str | None
    storage_method: str | None
    expires_at: datetime | None


# 추출 약 자동 검증 상태 응답 - REQ-DRUG-001, REQ-DRUG-005
class ExtractedDrugValidationResponse(BaseSerializerModel):
    name_match_status: Literal["exact", "candidate", "unmatched"]
    dosage_check_status: Literal["ok", "missing", "mismatch", "unknown"]
    needs_review: bool
    reason: str | None = None


# 추출 약 목록 항목 응답 - REQ-DOC-006
class ExtractedDrugItemResponse(BaseSerializerModel):
    extracted_med_id: int
    ocr_job_id: int
    patient_id: int
    name: str
    dosage_text: str | None
    frequency_text: str | None
    duration_text: str | None
    confidence: float | None
    mfds_info: ExtractedDrugMfdsInfoResponse | None = None
    validation: ExtractedDrugValidationResponse
    created_at: datetime


# 문서 추출 약 목록 조회 응답 - REQ-DOC-006
class DocumentDrugsResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    ocr_job_id: int | None
    ocr_status: OcrStatus | None
    barcode_detected: bool = False
    barcode_count: int = 0
    barcode_values: list[str] = Field(default_factory=list)
    items: list[ExtractedDrugItemResponse]
    total: int


# 추출 약 수정/확정 요청 항목 - REQ-DOC-007
class DocumentDrugPatchItemRequest(BaseModel):
    extracted_med_id: Annotated[int | None, Field(default=None, ge=1)]
    name: Annotated[str, Field(min_length=1, max_length=255)]
    dosage_text: Annotated[str | None, Field(default=None, max_length=255)]
    frequency_text: Annotated[str | None, Field(default=None, max_length=255)]
    duration_text: Annotated[str | None, Field(default=None, max_length=255)]
    confidence: Annotated[float | None, Field(default=None, ge=0, le=1)]


# 추출 약 수정/확정 요청 - REQ-DOC-007
class DocumentDrugPatchRequest(BaseModel):
    items: Annotated[list[DocumentDrugPatchItemRequest], Field(min_length=1)]
    replace_all: bool = False
    confirm: bool = True
    # 검수 필요 약 강제 확정 플래그 - REQ-DOC-007
    force_confirm: bool = False


# 추출 약 수정/확정 응답 - REQ-DOC-007
class DocumentDrugPatchResponse(BaseSerializerModel):
    document_id: int
    patient_id: int
    ocr_job_id: int
    confirmed: bool
    updated_count: int
    confirmed_patient_med_count: int
    items: list[ExtractedDrugItemResponse]


# 복약안내 카드 항목 응답 - REQ-DOC-007, REQ-DRUG-002, REQ-DRUG-003
class MedicationGuideItemResponse(BaseSerializerModel):
    patient_med_id: int
    patient_id: int
    display_name: str
    dosage: str | None
    frequency_text: str | None
    data_source: Literal["ocr_only", "ocr_mfds"]
    efficacy_summary: str | None
    dosage_instructions: list[str]
    precautions: list[str]
    storage_method: str | None
    prescribed_days: int | None
    prescribed_at: date | None
    expected_end_date: date | None
    interaction_warnings: list[str]
    source_document_id: int | None
    confirmed_at: datetime | None


# 환자 복약안내 조회 응답 - REQ-DOC-007, REQ-DRUG-002, REQ-DRUG-003
class MedicationGuideResponse(BaseSerializerModel):
    patient_id: int
    document_id: int | None
    include_other_active: bool
    total: int
    items: list[MedicationGuideItemResponse]


# 식약처 약 정보 검색 항목 응답 - REQ-DRUG-001, REQ-DRUG-002
class MfdsDrugItemResponse(BaseSerializerModel):
    item_seq: str
    item_name: str
    entp_name: str | None
    item_image: str | None = None
    efficacy: str | None
    dosage_info: str | None
    precautions: str | None


# 식약처 약 정보 검색 응답 - REQ-DRUG-001, REQ-DRUG-002, REQ-DRUG-003
class MfdsDrugSearchResponse(BaseSerializerModel):
    query: str
    total: int
    items: list[MfdsDrugItemResponse]


class BarcodeDecodeItemResponse(BaseSerializerModel):
    barcode_type: str
    barcode_value: str


class BarcodeDecodeResponse(BaseSerializerModel):
    total: int
    items: list[BarcodeDecodeItemResponse]
