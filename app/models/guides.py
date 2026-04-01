from __future__ import annotations

from enum import StrEnum

from tortoise import fields, models


class GuideStatus(StrEnum):
    # 가이드 생성 상태 enum
    GENERATING = "GENERATING"
    DONE = "DONE"
    FAILED = "FAILED"


class Guide(models.Model):
    # 가이드 본문/요약/생성 상태를 저장하는 메인 모델
    id = fields.BigIntField(primary_key=True)

    # 가이드 대상 환자
    patient = fields.ForeignKeyField(
        "models.Patient",
        related_name="guides",
        on_delete=fields.CASCADE,
    )

    # 가이드 생성 출처 문서
    document = fields.ForeignKeyField(
        "models.Document",
        related_name="guides",
        on_delete=fields.CASCADE,
    )

    # 가이드 처리 상태
    status = fields.CharEnumField(
        GuideStatus,
        max_length=20,
        default=GuideStatus.GENERATING,
    )

    # 같은 문서 기준 재생성 버전
    version = fields.IntField(default=1)

    # 환자용 자연어 가이드 본문
    content_text = fields.TextField(null=True)

    # 구조화된 가이드 JSON
    content_json = fields.JSONField(null=True)

    # 보호자용 요약 JSON
    caregiver_summary = fields.JSONField(null=True)

    # 책임 제한 문구
    disclaimer = fields.CharField(
        max_length=255,
        default="본 가이드는 의료 자문이 아닌 참고용 정보입니다.",
    )

    # 가이드 생성 요청 사용자
    created_by_user = fields.ForeignKeyField(
        "models.User",
        related_name="created_guides",
        null=True,
        on_delete=fields.SET_NULL,
    )

    # 재생성의 원본 가이드 추적
    regenerated_from = fields.ForeignKeyField(
        "models.Guide",
        related_name="regenerated_guides",
        null=True,
        on_delete=fields.SET_NULL,
    )

    # 실패 코드 저장
    failure_code = fields.CharField(
        max_length=100,
        null=True,
    )

    # 실패 상세 메시지 저장
    failure_message = fields.TextField(
        null=True,
    )

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "guides"
        indexes = (
            ("patient_id", "created_at"),
            ("patient_id", "version"),
            ("document_id", "created_at"),
            ("status",),
        )


class GuideFeedback(models.Model):
    # 가이드 만족도/피드백 저장 모델
    id = fields.BigIntField(primary_key=True)

    # 피드백 대상 가이드
    guide = fields.ForeignKeyField(
        "models.Guide",
        related_name="feedbacks",
        on_delete=fields.CASCADE,
    )

    # 피드백 작성 사용자
    user = fields.ForeignKeyField(
        "models.User",
        related_name="guide_feedbacks",
        on_delete=fields.CASCADE,
    )

    # 단순 평점
    rating = fields.IntField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "guide_feedback"
        indexes = (("guide_id", "created_at"),)
