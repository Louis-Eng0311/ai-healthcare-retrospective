# app/models/hospital_schedules.py

from tortoise import fields, models


class HospitalSchedule(models.Model):
    """
    병원 일정 테이블

    최소 CRUD 기준으로 구성:
    - 어떤 환자의 일정인지(patient)
    - 일정 제목(title)
    - 병원명(hospital_name)
    - 장소(location)
    - 예약 일시(scheduled_at)
    - 메모(description)
    - 누가 생성했는지(created_by_user)
    """

    id = fields.BigIntField(primary_key=True)

    # 어떤 환자의 병원 일정인지
    patient = fields.ForeignKeyField(
        "models.Patient",
        related_name="hospital_schedules",
        on_delete=fields.CASCADE,
    )

    # 일정 기본 정보
    title = fields.CharField(max_length=100)
    description = fields.TextField(null=True)
    hospital_name = fields.CharField(max_length=100, null=True)
    location = fields.CharField(max_length=255, null=True)

    # 방문/예약 일시
    scheduled_at = fields.DatetimeField()

    # 일정 등록자 (로그인 사용자 연결용)
    # 현재 인증 연동 전이면 null 허용 상태로 두는 것이 안전함
    created_by_user = fields.ForeignKeyField(
        "models.User",
        related_name="created_hospital_schedules",
        null=True,
        on_delete=fields.SET_NULL,
    )

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "hospital_schedules"
        ordering = ["scheduled_at"]
