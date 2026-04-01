# app/services/medication_intake_service.py
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import HTTPException, status

from app.dtos.medication_intake_dtos import (
    AdherenceResponse,
    AdherenceSummary,
    DailyIntakeStatus,
    IntakeCheckRequest,
    IntakeCheckResponse,
    IntakeItem,
    IntakeSkipRequest,
    IntakeSkipResponse,
    IntakeStatusResponse,
    IntakeUndoRequest,
    IntakeUndoResponse,
)
from app.models.documents import Document
from app.models.medications import PatientMed
from app.repositories.intake_log_repository import IntakeLogRepository
from app.repositories.med_schedule_repository import MedScheduleRepository

# 복약 예정 시각이 지난 뒤 몇 분까지는 pending 으로 보고,
# 그 이후에는 missed 로 계산할지에 대한 기준
GRACE_MINUTES = 60

# 요일 문자열 매핑
# Python weekday(): 월0 ~ 일6
DAY_NAME_TO_WEEKDAY = {
    "MON": 0,
    "TUE": 1,
    "WED": 2,
    "THU": 3,
    "FRI": 4,
    "SAT": 5,
    "SUN": 6,
}


def _parse_days_of_week(days_str: str | None) -> set[int] | None:
    """
    days_of_week 예시:
    - "1,2,3,4,5,6,7"  (구버전 숫자 방식)
    - "MON,TUE,WED,THU,FRI,SAT,SUN"  (현재 실제 DB 방식)
    - None / "" -> 매일 허용

    반환값:
    - Python weekday 기준 set[int]
      (월=0, 화=1, ..., 일=6)
    """
    if not days_str:
        return None

    result: set[int] = set()

    for raw in days_str.split(","):
        token = raw.strip().upper()
        if not token:
            continue

        # 숫자 형식 지원
        if token.isdigit():
            num = int(token)

            # 과거 규칙: 1=일요일, 7=토요일
            if 1 <= num <= 7:
                # 1(일) -> 6, 2(월) -> 0, ..., 7(토) -> 5
                converted = (num + 5) % 7
                result.add(converted)
                continue

            raise ValueError(f"지원하지 않는 숫자 요일 값입니다: {token}")

        # 문자열 형식 지원
        if token in DAY_NAME_TO_WEEKDAY:
            result.add(DAY_NAME_TO_WEEKDAY[token])
            continue

        raise ValueError(f"지원하지 않는 요일 형식입니다: {token}")

    return result if result else None


def _normalize_time_of_day(value: time | timedelta) -> time:
    """
    ORM이 TIME 컬럼을 datetime.time 으로 줄 수도 있고,
    datetime.timedelta 로 줄 수도 있어서 둘 다 처리한다.

    예:
    - datetime.time(8, 0)
    - timedelta(hours=8)
    """
    if isinstance(value, time):
        return value

    if isinstance(value, timedelta):
        total_seconds = int(value.total_seconds()) % (24 * 60 * 60)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return time(hour=hours, minute=minutes, second=seconds)

    raise TypeError(f"지원하지 않는 time_of_day 타입입니다: {type(value)}")


def _normalize_datetime_key(dt: datetime) -> datetime:
    """
    로그 매칭용 datetime 정규화

    - timezone 정보 제거
    - microsecond 제거

    DB에서 읽은 datetime과 code에서 만든 datetime을
    같은 기준으로 비교하기 위해 사용한다.
    """
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.replace(microsecond=0)


def _daterange(date_from: date, date_to: date) -> list[date]:
    """
    시작일 ~ 종료일까지 날짜 리스트 생성
    """
    days: list[date] = []
    cur = date_from
    while cur <= date_to:
        days.append(cur)
        cur += timedelta(days=1)
    return days


class MedicationIntakeService:
    def __init__(self) -> None:
        self.intake_repo = IntakeLogRepository()
        self.schedule_repo = MedScheduleRepository()

    async def check_medication(
        self,
        schedule_id: int,
        request: IntakeCheckRequest,
    ) -> IntakeCheckResponse:
        """
        복약 완료 체크

        처리 순서:
        1. schedule 존재 확인
        2. schedule_time 존재/활성 여부 확인
        3. schedule_time 이 해당 schedule 소속인지 확인
        4. scheduled_date 와 days_of_week 규칙이 맞는지 확인
        5. 동일 슬롯 로그 중복 체크
        6. intake_log 생성
        """
        schedule = await self.schedule_repo.get_schedule_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 스케줄을 찾을 수 없습니다.",
            )

        schedule_time = await self.schedule_repo.get_active_schedule_time_by_id(request.schedule_time_id)
        if schedule_time is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 시간 정보를 찾을 수 없습니다.",
            )

        if schedule_time.schedule_id != schedule.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 복약 시간은 요청한 스케줄에 속하지 않습니다.",
            )

        # 날짜가 스케줄 기간 내인지 확인
        if schedule.start_date and request.scheduled_date < schedule.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="복약 날짜가 스케줄 시작일보다 이전입니다.",
            )

        if schedule.end_date and request.scheduled_date > schedule.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="복약 날짜가 스케줄 종료일보다 이후입니다.",
            )

        # 요일 제한이 있다면 해당 날짜가 허용된 요일인지 확인
        allowed_days = _parse_days_of_week(schedule_time.days_of_week)
        if allowed_days is not None and request.scheduled_date.weekday() not in allowed_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 날짜는 이 복약 시간의 허용 요일이 아닙니다.",
            )

        # TIME 컬럼이 time/timedelta 둘 중 무엇으로 오든 정규화
        slot_time = _normalize_time_of_day(schedule_time.time_of_day)

        # 예약 시각 생성
        scheduled_at = datetime.combine(request.scheduled_date, slot_time)

        # taken_at 이 없으면 현재 시각을 기록
        actual_taken_at = request.taken_at or datetime.now()

        # 동일 슬롯 중복 기록 방지
        existing_log = await self.intake_repo.get_exact_log(
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
        )
        if existing_log is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 복약 체크가 완료된 슬롯입니다.",
            )

        created_log = await self.intake_repo.create_intake_log(
            patient_id=schedule.patient_id,
            patient_med_id=schedule.patient_med_id,
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
            taken_at=actual_taken_at,
            status="taken",
            note=request.note,
            recorded_by_user_id=request.recorded_by_user_id,
        )

        return IntakeCheckResponse(
            message="복약 체크가 완료되었습니다.",
            intake_log_id=created_log.id,
            patient_id=created_log.patient_id,
            patient_med_id=created_log.patient_med_id,
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
            taken_at=actual_taken_at,
            status="taken",
            note=request.note,
        )

    async def skip_medication(
        self,
        schedule_id: int,
        request: IntakeSkipRequest,
    ) -> IntakeSkipResponse:
        """
        복약 건너뛰기 처리

        처리 순서:
        1. schedule 존재 확인
        2. schedule_time 존재/활성 여부 확인
        3. schedule_time 이 해당 schedule 소속인지 확인
        4. scheduled_date 와 days_of_week 규칙이 맞는지 확인
        5. 동일 슬롯 로그 중복 체크
        6. intake_log 생성 (status='skipped')
        """
        schedule = await self.schedule_repo.get_schedule_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 스케줄을 찾을 수 없습니다.",
            )

        schedule_time = await self.schedule_repo.get_active_schedule_time_by_id(request.schedule_time_id)
        if schedule_time is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 시간 정보를 찾을 수 없습니다.",
            )

        if schedule_time.schedule_id != schedule.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 복약 시간은 요청한 스케줄에 속하지 않습니다.",
            )

        if schedule.start_date and request.scheduled_date < schedule.start_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="복약 날짜가 스케줄 시작일보다 이전입니다.",
            )

        if schedule.end_date and request.scheduled_date > schedule.end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="복약 날짜가 스케줄 종료일보다 이후입니다.",
            )

        allowed_days = _parse_days_of_week(schedule_time.days_of_week)
        if allowed_days is not None and request.scheduled_date.weekday() not in allowed_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 날짜는 이 복약 시간의 허용 요일이 아닙니다.",
            )

        slot_time = _normalize_time_of_day(schedule_time.time_of_day)
        scheduled_at = datetime.combine(request.scheduled_date, slot_time)

        existing_log = await self.intake_repo.get_exact_log(
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
        )
        if existing_log is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 처리된 복약 슬롯입니다.",
            )

        created_log = await self.intake_repo.create_intake_log(
            patient_id=schedule.patient_id,
            patient_med_id=schedule.patient_med_id,
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
            taken_at=None,
            status="skipped",
            note=request.note,
            recorded_by_user_id=request.recorded_by_user_id,
        )

        return IntakeSkipResponse(
            message="복약 건너뛰기가 기록되었습니다.",
            intake_log_id=created_log.id,
            patient_id=created_log.patient_id,
            patient_med_id=created_log.patient_med_id,
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
            status="skipped",
            note=request.note,
        )

    async def undo_medication(
        self,
        schedule_id: int,
        request: IntakeUndoRequest,
    ) -> IntakeUndoResponse:
        """
        복약 체크 취소
        """
        schedule = await self.schedule_repo.get_schedule_by_id(schedule_id)
        if schedule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 스케줄을 찾을 수 없습니다.",
            )

        schedule_time = await self.schedule_repo.get_schedule_time_by_id(request.schedule_time_id)
        if schedule_time is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="복약 시간 정보를 찾을 수 없습니다.",
            )

        if schedule_time.schedule_id != schedule.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="해당 복약 시간은 요청한 스케줄에 속하지 않습니다.",
            )

        slot_time = _normalize_time_of_day(schedule_time.time_of_day)
        scheduled_at = datetime.combine(request.scheduled_date, slot_time)

        existing_log = await self.intake_repo.get_exact_log(
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
        )
        if existing_log is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="취소할 복약 기록이 없습니다.",
            )

        deleted_id = existing_log.id
        await self.intake_repo.delete_log(existing_log)

        return IntakeUndoResponse(
            message="복약 체크가 취소되었습니다.",
            deleted_intake_log_id=deleted_id,
            schedule_id=schedule.id,
            schedule_time_id=schedule_time.id,
            scheduled_at=scheduled_at,
        )

    async def get_patient_intake_status(  # noqa: C901
        self,
        patient_id: int,
        date_from: date,
        date_to: date,
        now: datetime | None = None,
    ) -> IntakeStatusResponse:
        """
        기간 내 복약 현황 조회
        """
        if date_from > date_to:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from 날짜는 to 날짜보다 이후일 수 없습니다.",
            )

        if now is None:
            now = datetime.now()

        allowed_patient_med_ids = await self._resolve_allowed_patient_med_ids(patient_id=patient_id)
        schedules = await self.schedule_repo.list_active_schedules_by_patient_in_range(
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
        )
        if allowed_patient_med_ids:
            schedules = [schedule for schedule in schedules if schedule.patient_med_id in allowed_patient_med_ids]
        else:
            schedules = []
        schedule_ids = [s.id for s in schedules]

        schedule_times = await self.schedule_repo.list_times_by_schedule_ids(schedule_ids)

        times_by_schedule: dict[int, list] = {}
        for t in schedule_times:
            times_by_schedule.setdefault(t.schedule_id, []).append(t)

        start_dt = datetime.combine(date_from, time.min)
        end_dt = datetime.combine(date_to + timedelta(days=1), time.min)

        logs = await self.intake_repo.list_logs_by_patient_and_range(
            patient_id=patient_id,
            start_dt=start_dt,
            end_dt=end_dt,
        )

        log_map: dict[tuple[int, datetime], object] = {}
        for log in logs:
            normalized_log_dt = _normalize_datetime_key(log.scheduled_at)
            log_map[(log.schedule_time_id, normalized_log_dt)] = log

        grace = timedelta(minutes=GRACE_MINUTES)

        daily_list: list[DailyIntakeStatus] = []
        expected_total = 0
        taken = 0
        missed = 0
        pending = 0
        skipped = 0

        for day in _daterange(date_from, date_to):
            items: list[IntakeItem] = []

            for schedule in schedules:
                if schedule.start_date and day < schedule.start_date:
                    continue
                if schedule.end_date and day > schedule.end_date:
                    continue

                for schedule_time in times_by_schedule.get(schedule.id, []):
                    allowed_days = _parse_days_of_week(schedule_time.days_of_week)
                    if allowed_days is not None and day.weekday() not in allowed_days:
                        continue

                    slot_time = _normalize_time_of_day(schedule_time.time_of_day)
                    scheduled_at = datetime.combine(day, slot_time)
                    scheduled_at_key = _normalize_datetime_key(scheduled_at)
                    expected_total += 1

                    log = log_map.get((schedule_time.id, scheduled_at_key))

                    if log:
                        status_value = log.status

                        if status_value == "taken":
                            taken += 1
                        elif status_value == "missed":
                            missed += 1
                        elif status_value == "skipped":
                            skipped += 1
                        else:
                            status_value = "pending"
                            pending += 1

                        items.append(
                            IntakeItem(
                                schedule_id=schedule.id,
                                schedule_time_id=schedule_time.id,
                                patient_med_id=schedule.patient_med_id,
                                medication_name=getattr(getattr(schedule, "patient_med", None), "display_name", None),
                                scheduled_at=scheduled_at,
                                status=status_value,
                                taken_at=log.taken_at,
                                note=log.note,
                            )
                        )
                    else:
                        if now >= scheduled_at + grace:
                            status_value = "missed"
                            missed += 1
                        else:
                            status_value = "pending"
                            pending += 1

                        items.append(
                            IntakeItem(
                                schedule_id=schedule.id,
                                schedule_time_id=schedule_time.id,
                                patient_med_id=schedule.patient_med_id,
                                medication_name=getattr(getattr(schedule, "patient_med", None), "display_name", None),
                                scheduled_at=scheduled_at,
                                status=status_value,
                                taken_at=None,
                                note=None,
                            )
                        )

            items.sort(key=lambda x: x.scheduled_at)
            daily_list.append(DailyIntakeStatus(day=day, items=items))

        overall_rate = (taken / expected_total) if expected_total else 0.0
        completed_denominator = taken + missed + skipped
        completed_rate = (taken / completed_denominator) if completed_denominator else None

        summary = AdherenceSummary(
            expected_total=expected_total,
            taken=taken,
            missed=missed,
            pending=pending,
            skipped=skipped,
            overall_rate=round(overall_rate, 4),
            completed_rate=round(completed_rate, 4) if completed_rate is not None else None,
        )

        return IntakeStatusResponse(
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            days=daily_list,
            summary=summary,
        )

    async def _resolve_allowed_patient_med_ids(self, *, patient_id: int) -> set[int]:
        deleted_document_ids = await Document.filter(patient_id=patient_id, status="deleted").values_list(
            "id", flat=True
        )
        patient_meds_query = PatientMed.filter(patient_id=patient_id, is_active=True)
        if deleted_document_ids:
            patient_meds_query = patient_meds_query.exclude(source_document_id__in=list(deleted_document_ids))
        patient_med_ids = await patient_meds_query.values_list("id", flat=True)
        return set(patient_med_ids)

    async def get_patient_adherence(
        self,
        patient_id: int,
        date_from: date,
        date_to: date,
        now: datetime | None = None,
    ) -> AdherenceResponse:
        """
        복약 이행률 조회
        """
        status_result = await self.get_patient_intake_status(
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            now=now,
        )

        return AdherenceResponse(
            patient_id=patient_id,
            date_from=date_from,
            date_to=date_to,
            summary=status_result.summary,
        )
