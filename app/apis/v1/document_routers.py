from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.responses import ORJSONResponse as Response

from app.dependencies.security import get_request_user
from app.dtos.documents import (
    BarcodeDecodeResponse,
    DocumentDeleteResponse,
    DocumentDrugPatchRequest,
    DocumentDrugPatchResponse,
    DocumentDrugsResponse,
    DocumentListQuery,
    DocumentListResponse,
    DocumentOcrRetryResponse,
    DocumentOcrStatusResponse,
    DocumentOcrTextResponse,
    DocumentRenameRequest,
    DocumentRenameResponse,
    DocumentUploadResponse,
    MedicationGuideResponse,
    MfdsDrugSearchResponse,
)
from app.models.users import User
from app.services.documents import DocumentService
from app.services.mfds import MfdsService
from app.services.ocr import OcrService

document_router = APIRouter(prefix="/documents", tags=["documents"])


# 대상 PATIENT 귀속 + 문서 업로드/OCR 작업 생성 - REQ-USER-008, REQ-DOC-003
@document_router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
    patient_id: Annotated[int | None, Form(ge=1)] = None,
    title: Annotated[str | None, Form(max_length=255)] = None,
) -> Response:
    result = await document_service.upload_document(user=user, file=file, patient_id=patient_id, title=title)
    return Response(result.model_dump(), status_code=status.HTTP_201_CREATED)


# 문서 목록 조회 및 필터 - REQ-DOC-002
@document_router.get("", response_model=DocumentListResponse, status_code=status.HTTP_200_OK)
async def list_documents(
    query: Annotated[DocumentListQuery, Depends()],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.list_documents(user=user, query=query)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# 문서 soft delete(권한 검증 포함) - REQ-DOC-001
@document_router.delete("/{document_id}", response_model=DocumentDeleteResponse, status_code=status.HTTP_200_OK)
async def soft_delete_document(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.soft_delete_document(user=user, document_id=document_id)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# 문서명 변경 - REQ-DOC-002
@document_router.patch("/{document_id}/title", response_model=DocumentRenameResponse, status_code=status.HTTP_200_OK)
async def rename_document(
    document_id: Annotated[int, Path(ge=1)],
    payload: DocumentRenameRequest,
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.rename_document(user=user, document_id=document_id, payload=payload)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


@document_router.get("/{document_id}/file", status_code=status.HTTP_200_OK)
async def get_document_file(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> FileResponse:
    file_info = await document_service.get_document_file(user=user, document_id=document_id)
    return FileResponse(
        path=file_info.file_path,
        filename=file_info.download_name,
        media_type=file_info.media_type,
    )


# 추출 약 목록 조회 - REQ-DOC-006
@document_router.get("/{document_id}/drugs", response_model=DocumentDrugsResponse, status_code=status.HTTP_200_OK)
async def get_document_drugs(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
    include_mfds: Annotated[bool, Query()] = True,
) -> Response:
    result = await document_service.get_document_drugs(user=user, document_id=document_id, include_mfds=include_mfds)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# 추출 약 수정/확정 - REQ-DOC-007
@document_router.patch("/{document_id}/drugs", response_model=DocumentDrugPatchResponse, status_code=status.HTTP_200_OK)
async def patch_document_drugs(
    document_id: Annotated[int, Path(ge=1)],
    payload: DocumentDrugPatchRequest,
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.patch_document_drugs(user=user, document_id=document_id, payload=payload)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# 환자 복약안내 카드 조회 - REQ-DOC-007, REQ-DRUG-002, REQ-DRUG-003
@document_router.get("/medication-guide", response_model=MedicationGuideResponse, status_code=status.HTTP_200_OK)
async def get_medication_guide(
    patient_id: Annotated[int, Query(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
    document_id: Annotated[int | None, Query(ge=1)] = None,
    include_other_active: Annotated[bool, Query()] = False,
) -> Response:
    result = await document_service.get_medication_guide(
        user=user,
        patient_id=patient_id,
        document_id=document_id,
        include_other_active=include_other_active,
    )
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# OCR 처리 상태 조회 - REQ-DOC-003
@document_router.get("/{document_id}/status", response_model=DocumentOcrStatusResponse, status_code=status.HTTP_200_OK)
async def get_document_ocr_status(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.get_document_ocr_status(user=user, document_id=document_id)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# OCR 결과 원문 조회 - REQ-DOC-003
@document_router.get("/{document_id}/ocr-text", response_model=DocumentOcrTextResponse, status_code=status.HTTP_200_OK)
async def get_document_ocr_text(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.get_document_ocr_text(user=user, document_id=document_id)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# OCR 재시도 요청 - REQ-DOC-008
@document_router.post(
    "/{document_id}/retry", response_model=DocumentOcrRetryResponse, status_code=status.HTTP_202_ACCEPTED
)
async def retry_document_ocr(
    document_id: Annotated[int, Path(ge=1)],
    user: Annotated[User, Depends(get_request_user)],
    ocr_service: Annotated[OcrService, Depends(OcrService)],
) -> Response:
    result = await ocr_service.retry_document_ocr(user=user, document_id=document_id)
    return Response(result.model_dump(), status_code=status.HTTP_202_ACCEPTED)


@document_router.post("/barcodes/decode", response_model=BarcodeDecodeResponse, status_code=status.HTTP_200_OK)
async def decode_barcodes(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_request_user)],
    document_service: Annotated[DocumentService, Depends(DocumentService)],
) -> Response:
    result = await document_service.decode_barcodes(user=user, file=file)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)


# 식약처 약 정보 검색 - REQ-DRUG-001, REQ-DRUG-002, REQ-DRUG-003
@document_router.get("/mfds/search", response_model=MfdsDrugSearchResponse, status_code=status.HTTP_200_OK)
async def search_mfds_drug_info(
    user: Annotated[User, Depends(get_request_user)],  # noqa: ARG001
    mfds_service: Annotated[MfdsService, Depends(MfdsService)],
    drug_name: Annotated[str, Query(min_length=1, max_length=100)],
    num_of_rows: Annotated[int, Query(ge=1, le=20)] = 5,
) -> Response:
    result = await mfds_service.search_easy_drug_info(drug_name=drug_name, num_of_rows=num_of_rows)
    return Response(result.model_dump(), status_code=status.HTTP_200_OK)
