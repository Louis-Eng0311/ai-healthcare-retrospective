from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError
from tortoise.transactions import in_transaction

from app.dtos.guide import (
    GuideDetailData,
    GuideDetailResponse,
    GuideGenerateData,
    GuideGenerateResponse,
    GuideListData,
    GuideListItem,
    GuideListResponse,
    GuideRegenerateData,
    GuideRegenerateResponse,
)
from app.models.documents import Document, OcrJob
from app.models.guides import Guide, GuideStatus
from app.models.medications import DrugInfoCache, PatientMed
from app.models.patients import PatientProfile
from app.models.schedules import MedSchedule, MedScheduleTime
from app.services.kids_client import KIDSClient
from app.services.mfds_client import MFDSClient
from app.services.rag import (
    build_rag_context,
    extract_external_blocks,
    extract_meds_blocks,
    extract_profile_blocks,
    extract_schedule_blocks,
)

REDIS_URL = (os.getenv("REDIS_URL", "redis://localhost:6379/0") or "").strip()
AI_WORKER_QUEUE = (os.getenv("AI_WORKER_QUEUE", "ai_tasks") or "").strip()
GUIDE_DISCLAIMER = "본 가이드는 의료 자문이 아닌 참고용 건강 정보입니다."


class GuideServiceError(Exception):
    def __init__(self, *, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class GuideContextBundle:
    document: Document
    patient_id: int
    profile: PatientProfile | None
    meds: list[dict[str, Any]]
    schedules: list[dict[str, Any]]
    mfds_evidence: list[dict[str, Any]]
    kids_evidence: list[dict[str, Any]]
    rag_context: list[dict[str, Any]]


class GuideService:
    # 가이드 생성 요청 처리
    @staticmethod
    async def create_guide_generation(
        *,
        document_id: int,
        requester_user_id: int,
    ) -> GuideGenerateResponse:
        document = await GuideService._get_document_or_raise(document_id=document_id)
        await GuideService._assert_document_ready(document=document)

        patient_id = GuideService._get_document_patient_id(document)
        meds = await GuideService._get_active_confirmed_meds(
            patient_id=patient_id,
            document_id=document_id,
        )
        if not meds:
            raise GuideServiceError(
                status_code=422,
                code="DRUGS_NOT_CONFIRMED",
                message="확정된 복용 약이 없어 가이드를 생성할 수 없습니다.",
            )

        next_version = await GuideService._get_next_version(
            patient_id=patient_id,
            document_id=document_id,
        )

        async with in_transaction():
            guide = await Guide.create(
                patient_id=patient_id,
                document_id=document_id,
                status=GuideStatus.GENERATING,
                version=next_version,
                disclaimer=GUIDE_DISCLAIMER,
                created_by_user_id=requester_user_id,
            )

        await GuideService._enqueue_generate_task(
            guide_id=int(guide.id),
            document_id=document_id,
            patient_id=patient_id,
        )

        return GuideGenerateResponse(
            success=True,
            data=GuideGenerateData(
                guide_id=int(guide.id),
                status=str(guide.status),
            ),
        )

    # 가이드 목록 조회
    @staticmethod
    async def list_guides(*, patient_id: int) -> GuideListResponse:
        rows = await Guide.filter(patient_id=patient_id).order_by("-created_at", "-id").all()

        items = [
            GuideListItem(
                guide_id=int(row.id),
                patient_id=GuideService._get_guide_patient_id(row),
                document_id=GuideService._get_guide_document_id(row),
                version=int(row.version),
                status=str(row.status),
                created_at=row.created_at,
            )
            for row in rows
        ]

        return GuideListResponse(
            success=True,
            data=GuideListData(
                items=items,
                total=len(items),
            ),
        )

    # 가이드 상세 조회
    @staticmethod
    async def get_guide_detail(*, guide_id: int) -> GuideDetailResponse:
        guide = await Guide.get_or_none(id=guide_id)
        if not guide:
            raise GuideServiceError(
                status_code=404,
                code="GUIDE_NOT_FOUND",
                message="가이드를 찾을 수 없습니다.",
            )

        return GuideDetailResponse(
            success=True,
            data=GuideDetailData(
                guide_id=int(guide.id),
                patient_id=GuideService._get_guide_patient_id(guide),
                document_id=GuideService._get_guide_document_id(guide),
                version=int(guide.version),
                status=str(guide.status),
                content_text=guide.content_text,
                content_json=GuideService._normalize_json_field(guide.content_json),
                caregiver_summary=GuideService._normalize_json_field(guide.caregiver_summary),
                disclaimer=guide.disclaimer or GUIDE_DISCLAIMER,
                created_at=guide.created_at,
                updated_at=guide.updated_at,
            ),
        )

    # 가이드 재생성 요청 처리
    @staticmethod
    async def regenerate_guide(
        *,
        guide_id: int,
        requester_user_id: int,
    ) -> GuideRegenerateResponse:
        origin = await Guide.get_or_none(id=guide_id)
        if not origin:
            raise GuideServiceError(
                status_code=404,
                code="GUIDE_NOT_FOUND",
                message="재생성할 가이드를 찾을 수 없습니다.",
            )

        document_id = GuideService._get_guide_document_id(origin)
        patient_id = GuideService._get_guide_patient_id(origin)

        document = await GuideService._get_document_or_raise(document_id=document_id)
        await GuideService._assert_document_ready(document=document)

        meds = await GuideService._get_active_confirmed_meds(
            patient_id=patient_id,
            document_id=document_id,
        )
        if not meds:
            raise GuideServiceError(
                status_code=422,
                code="DRUGS_NOT_CONFIRMED",
                message="확정된 복용 약이 없어 가이드를 재생성할 수 없습니다.",
            )

        next_version = await GuideService._get_next_version(
            patient_id=patient_id,
            document_id=document_id,
        )

        async with in_transaction():
            new_guide = await Guide.create(
                patient_id=patient_id,
                document_id=document_id,
                status=GuideStatus.GENERATING,
                version=next_version,
                disclaimer=GUIDE_DISCLAIMER,
                created_by_user_id=requester_user_id,
                regenerated_from_id=int(origin.id),
            )

        await GuideService._enqueue_generate_task(
            guide_id=int(new_guide.id),
            document_id=document_id,
            patient_id=patient_id,
        )

        return GuideRegenerateResponse(
            success=True,
            data=GuideRegenerateData(
                guide_id=int(new_guide.id),
                status=str(new_guide.status),
            ),
        )

    # worker용 가이드 생성 컨텍스트 구성
    @staticmethod
    async def build_generation_context(*, document_id: int) -> GuideContextBundle:
        document = await GuideService._get_document_or_raise(document_id=document_id)
        await GuideService._assert_document_ready(document=document)

        patient_id = GuideService._get_document_patient_id(document)

        profile = await PatientProfile.get_or_none(
            patient_id=patient_id,
            is_deleted=False,
        )
        meds = await GuideService._get_active_confirmed_meds(
            patient_id=patient_id,
            document_id=document_id,
        )
        if not meds:
            raise GuideServiceError(
                status_code=422,
                code="DRUGS_NOT_CONFIRMED",
                message="확정된 복용 약이 없어 가이드 생성 컨텍스트를 만들 수 없습니다.",
            )

        schedules = await GuideService._get_active_schedules(patient_id=patient_id)
        mfds_evidence = await GuideService._build_mfds_evidence(meds=meds)
        kids_evidence = await GuideService._build_kids_evidence(
            meds=meds,
            profile=profile,
        )
        rag_context = await GuideService._build_rag_context(
            meds=meds,
            schedules=schedules,
            profile=profile,
            mfds_evidence=mfds_evidence,
            kids_evidence=kids_evidence,
        )

        return GuideContextBundle(
            document=document,
            patient_id=patient_id,
            profile=profile,
            meds=meds,
            schedules=schedules,
            mfds_evidence=mfds_evidence,
            kids_evidence=kids_evidence,
            rag_context=rag_context,
        )

    # 문서 조회
    @staticmethod
    async def _get_document_or_raise(*, document_id: int) -> Document:
        document = await Document.get_or_none(id=document_id, deleted_at=None)
        if not document:
            raise GuideServiceError(
                status_code=404,
                code="DOCUMENT_NOT_FOUND",
                message="문서를 찾을 수 없습니다.",
            )
        return document

    # 문서의 환자 ID 추출
    @staticmethod
    def _get_document_patient_id(document: Document) -> int:
        patient_id = getattr(document, "patient_id", None)
        if patient_id is None:
            raise GuideServiceError(
                status_code=500,
                code="DOCUMENT_PATIENT_MISSING",
                message="문서에 연결된 환자 정보가 없습니다.",
            )
        return int(patient_id)

    # 가이드의 환자 ID 추출
    @staticmethod
    def _get_guide_patient_id(guide: Guide) -> int:
        patient_id = getattr(guide, "patient_id", None)
        if patient_id is None:
            raise GuideServiceError(
                status_code=500,
                code="GUIDE_PATIENT_MISSING",
                message="가이드에 연결된 환자 정보가 없습니다.",
            )
        return int(patient_id)

    # 가이드의 문서 ID 추출
    @staticmethod
    def _get_guide_document_id(guide: Guide) -> int:
        document_id = getattr(guide, "document_id", None)
        if document_id is None:
            raise GuideServiceError(
                status_code=500,
                code="GUIDE_DOCUMENT_MISSING",
                message="가이드에 연결된 문서 정보가 없습니다.",
            )
        return int(document_id)

    # OCR 완료 여부 검증
    @staticmethod
    async def _assert_document_ready(*, document: Document) -> None:
        document_status = (getattr(document, "status", "") or "").upper()

        latest_job = await OcrJob.filter(document_id=int(document.id)).order_by("-created_at", "-id").first()
        latest_job_status = (getattr(latest_job, "status", "") or "").upper() if latest_job else ""

        ready_statuses = {"OCR_DONE", "DONE", "COMPLETED", "SUCCESS"}

        if document_status in ready_statuses:
            return
        if latest_job_status in ready_statuses:
            return

        raise GuideServiceError(
            status_code=422,
            code="OCR_NOT_DONE",
            message="OCR 미완료 상태 문서는 가이드를 생성할 수 없습니다.",
        )

    # 현재 복용중 확정 약 조회
    @staticmethod
    async def _get_active_confirmed_meds(
        *,
        patient_id: int,
        document_id: int,
    ) -> list[dict[str, Any]]:
        rows = (
            await PatientMed.filter(
                patient_id=patient_id,
                is_active=True,
                confirmed_at__not_isnull=True,
            )
            .prefetch_related("drug_info_cache", "drug_catalog")
            .order_by("id")
            .all()
        )

        # 우선: 해당 document에서 확정된 약
        document_scoped = [row for row in rows if getattr(row, "source_document_id", None) == document_id]
        selected_rows = document_scoped or rows

        results: list[dict[str, Any]] = []
        for row in selected_rows:
            cache: DrugInfoCache | None = getattr(row, "drug_info_cache", None)
            catalog = getattr(row, "drug_catalog", None)

            results.append(
                {
                    "patient_med_id": int(row.id),
                    "display_name": row.display_name,
                    "dosage": row.dosage,
                    "route": row.route,
                    "notes": row.notes,
                    "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
                    "source_document_id": getattr(row, "source_document_id", None),
                    "source_ocr_job_id": getattr(row, "source_ocr_job_id", None),
                    "source_extracted_med_id": getattr(row, "source_extracted_med_id", None),
                    "drug_info_cache_id": getattr(row, "drug_info_cache_id", None),
                    "drug_catalog_id": getattr(row, "drug_catalog_id", None),
                    "drug_info": {
                        "drug_name_display": cache.drug_name_display if cache else None,
                        "manufacturer": cache.manufacturer if cache else None,
                        "efficacy": cache.efficacy if cache else None,
                        "dosage_info": cache.dosage_info if cache else None,
                        "precautions": cache.precautions if cache else None,
                        "interactions": cache.interactions if cache else None,
                        "side_effects": cache.side_effects if cache else None,
                        "storage_method": cache.storage_method if cache else None,
                    },
                    "drug_catalog": {
                        "name": catalog.name if catalog else None,
                        "ingredients": catalog.ingredients if catalog else None,
                        "warnings": catalog.warnings if catalog else None,
                        "manufacturer": catalog.manufacturer if catalog else None,
                    },
                }
            )

        return results

    # 현재 활성 복약 일정 조회
    @staticmethod
    async def _get_active_schedules(*, patient_id: int) -> list[dict[str, Any]]:
        schedules = await MedSchedule.filter(
            patient_id=patient_id,
            status="active",
        ).all()

        if not schedules:
            return []

        schedule_ids = [int(s.id) for s in schedules]
        schedule_times = await MedScheduleTime.filter(
            schedule_id__in=schedule_ids,
            is_active=True,
        ).all()

        time_map: dict[int, list[dict[str, Any]]] = {}
        for item in schedule_times:
            schedule_id = int(item.schedule_id)
            time_map.setdefault(schedule_id, []).append(
                {
                    "time_of_day": str(item.time_of_day) if item.time_of_day else None,
                    "days_of_week": item.days_of_week,
                }
            )

        result: list[dict[str, Any]] = []
        for schedule in schedules:
            result.append(
                {
                    "schedule_id": int(schedule.id),
                    "patient_med_id": int(schedule.patient_med_id),
                    "start_date": str(schedule.start_date) if schedule.start_date else None,
                    "end_date": str(schedule.end_date) if schedule.end_date else None,
                    "status": schedule.status,
                    "times": time_map.get(int(schedule.id), []),
                }
            )

        return result

    # MFDS 보강 근거 구성
    @staticmethod
    async def _build_mfds_evidence(*, meds: list[dict[str, Any]]) -> list[dict[str, Any]]:
        client = MFDSClient()
        if not client.is_enabled():
            return []

        evidence: list[dict[str, Any]] = []

        for med in meds:
            display_name = med.get("display_name")
            if not display_name:
                continue

            try:
                guide_info = await client.fetch_guide_drug_info(display_name)
                evidence.append(guide_info)
            except Exception:
                # 개별 약 실패는 전체 가이드 실패로 넘기지 않고 건너뜀
                continue

        return evidence

    # KIDS 안전성 근거 구성
    @staticmethod
    async def _build_kids_evidence(
        *,
        meds: list[dict[str, Any]],
        profile: PatientProfile | None,
    ) -> list[dict[str, Any]]:
        del profile

        client = KIDSClient()
        if not client.is_enabled():
            return []

        evidence: list[dict[str, Any]] = []

        for med in meds[:5]:
            drug_name = str(med.get("display_name") or "").strip()
            if not drug_name:
                continue

            try:
                items = await client.search_safety_evidence(drug_name)
                evidence.extend(items)
            except Exception:
                continue

        return evidence[:10]

    # RAG 참고 근거 구성
    @staticmethod
    async def _build_rag_context(
        *,
        meds: list[dict[str, Any]],
        schedules: list[dict[str, Any]],
        profile: PatientProfile | None,
        mfds_evidence: list[dict[str, Any]],
        kids_evidence: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        # meds 텍스트
        meds_lines: list[str] = []
        for med in meds:
            display_name = med.get("display_name") or "약 이름 없음"
            dosage = med.get("dosage")
            route = med.get("route")
            notes = med.get("notes")

            chunks = [display_name]
            if dosage:
                chunks.append(f"용량={dosage}")
            if route:
                chunks.append(f"투여경로={route}")
            if notes:
                chunks.append(f"메모={notes}")

            meds_lines.append("- " + " / ".join(chunks))

        meds_text = "\n".join(meds_lines) if meds_lines else "현재 복용 약 정보 없음"

        # schedules 텍스트
        med_name_map: dict[int, str] = {}
        for med in meds:
            patient_med_id = med.get("patient_med_id")
            display_name = med.get("display_name")
            if patient_med_id is not None and display_name:
                med_name_map[int(patient_med_id)] = str(display_name)

        schedule_lines: list[str] = []
        for schedule in schedules:
            patient_med_id = int(schedule.get("patient_med_id"))
            med_name = med_name_map.get(patient_med_id, f"patient_med_id={patient_med_id}")
            times = schedule.get("times") or []

            if not times:
                schedule_lines.append(f"- {med_name}: 시간 정보 없음")
                continue

            for item in times:
                time_text = item.get("time_of_day") or "시간 미설정"
                days_text = item.get("days_of_week") or "요일 정보 없음"
                schedule_lines.append(f"- {med_name}: 시간={time_text} / 요일={days_text}")

        schedule_text = "\n".join(schedule_lines) if schedule_lines else "등록된 복약 일정 없음"

        profile_blocks = extract_profile_blocks(profile)
        schedule_blocks = extract_schedule_blocks(schedule_text)
        meds_blocks = extract_meds_blocks(meds_text)
        external_blocks = extract_external_blocks(
            mfds_evidence=mfds_evidence,
            kids_evidence=kids_evidence,
        )

        return build_rag_context(
            intent="guide",
            guide_blocks=[],
            profile_blocks=profile_blocks,
            schedule_blocks=schedule_blocks,
            meds_blocks=meds_blocks,
            external_blocks=external_blocks,
            limit=8,
        )

    # 다음 가이드 버전 계산
    @staticmethod
    async def _get_next_version(
        *,
        patient_id: int,
        document_id: int,
    ) -> int:
        latest = await Guide.filter(patient_id=patient_id, document_id=document_id).order_by("-version", "-id").first()
        if not latest:
            return 1
        return int(latest.version) + 1

    # AI worker 큐 작업 등록
    @staticmethod
    async def _enqueue_generate_task(
        *,
        guide_id: int,
        document_id: int,
        patient_id: int,
    ) -> None:
        payload = {
            "task": "generate_guide",
            "guide_id": guide_id,
            "document_id": document_id,
            "patient_id": patient_id,
            "requested_at": datetime.now(UTC).isoformat(),
        }

        client = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            await client.lpush(AI_WORKER_QUEUE, json.dumps(payload, ensure_ascii=False))
        except RedisError as exc:
            guide = await Guide.get_or_none(id=guide_id)
            if guide:
                guide.status = GuideStatus.FAILED
                guide.failure_code = "QUEUE_UNAVAILABLE"
                guide.failure_message = str(exc)
                await guide.save(update_fields=["status", "failure_code", "failure_message", "updated_at"])

            raise GuideServiceError(
                status_code=503,
                code="QUEUE_UNAVAILABLE",
                message="가이드 생성 작업을 큐에 등록하지 못했습니다.",
            ) from exc
        finally:
            await client.aclose()

    # JSON 필드 정규화
    @staticmethod
    def _normalize_json_field(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"raw": value}
        return {"raw": value}
