import logging
from datetime import date, datetime, timedelta

from app.dtos.dashboard import ChartDataPoint, DashboardResponse, DashboardStatsResponse, OCRAnalysis
from app.models.chat import ChatSession
from app.models.documents import OcrJob
from app.models.guides import Guide, GuideStatus
from app.models.users import User

logger = logging.getLogger(__name__)

OCR_SUCCESS_STATUSES = ("success", "completed")
OCR_FAILURE_STATUSES = ("failed",)


class DashboardService:
    @staticmethod
    async def get_dashboard_data(period_days: int = 7) -> DashboardResponse:
        today = date.today()
        yesterday = today - timedelta(days=1)
        period_start = today - timedelta(days=period_days)

        stats = await DashboardService._build_stats(today, yesterday)
        guide_trend = await DashboardService._build_guide_trend(period_start, period_days)
        chatbot_trend = await DashboardService._build_chatbot_trend(period_start, period_days)
        ocr_analysis = await DashboardService._build_ocr_analysis()

        return DashboardResponse(
            stats=stats,
            guide_trend=guide_trend,
            chatbot_trend=chatbot_trend,
            ocr_analysis=ocr_analysis,
        )

    @staticmethod
    async def _build_stats(today: date, yesterday: date) -> DashboardStatsResponse:
        total_users = await User.filter(is_active=True).count()
        yesterday_users = await User.filter(is_active=True, created_at__lt=today).count()
        users_change = ((total_users - yesterday_users) / yesterday_users * 100) if yesterday_users > 0 else 0

        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())
        yesterday_start = datetime.combine(yesterday, datetime.min.time())
        yesterday_end = datetime.combine(yesterday, datetime.max.time())

        today_guides, yesterday_guides = await DashboardService._get_guide_counts(
            today_start, today_end, yesterday_start, yesterday_end
        )
        guides_change = ((today_guides - yesterday_guides) / yesterday_guides * 100) if yesterday_guides > 0 else 0

        ocr_success_rate, yesterday_ocr_rate = await DashboardService._get_ocr_rates(
            today_start, today_end, yesterday_start, yesterday_end
        )
        ocr_change = ocr_success_rate - yesterday_ocr_rate

        today_chatbot, yesterday_chatbot = await DashboardService._get_chatbot_counts(
            today_start=today_start,
            today_end=today_end,
            yesterday_start=yesterday_start,
            yesterday_end=yesterday_end,
        )
        chatbot_change = ((today_chatbot - yesterday_chatbot) / yesterday_chatbot * 100) if yesterday_chatbot > 0 else 0

        system_errors, system_errors_change = await DashboardService._get_system_errors(
            today_start=today_start,
            today_end=today_end,
            yesterday_start=yesterday_start,
            yesterday_end=yesterday_end,
        )

        return DashboardStatsResponse(
            total_users=total_users,
            today_guides=today_guides,
            ocr_success_rate=round(ocr_success_rate, 1),
            today_chatbot_requests=today_chatbot,
            system_errors=system_errors,
            total_users_change=round(users_change, 1),
            today_guides_change=round(guides_change, 1),
            ocr_success_rate_change=round(ocr_change, 1),
            today_chatbot_requests_change=round(chatbot_change, 1),
            system_errors_change=system_errors_change,
        )

    @staticmethod
    async def _get_guide_counts(
        today_start: datetime,
        today_end: datetime,
        yesterday_start: datetime,
        yesterday_end: datetime,
    ) -> tuple[int, int]:
        try:
            today_guides = await Guide.filter(created_at__gte=today_start, created_at__lte=today_end).count()
            yesterday_guides = await Guide.filter(
                created_at__gte=yesterday_start, created_at__lte=yesterday_end
            ).count()
        except Exception:
            logger.exception("failed to build guide counts")
            today_guides = 0
            yesterday_guides = 0
        return today_guides, yesterday_guides

    @staticmethod
    async def _get_ocr_rates(
        today_start: datetime,
        today_end: datetime,
        yesterday_start: datetime,
        yesterday_end: datetime,
    ) -> tuple[float, float]:
        try:
            today_ocr_jobs = await OcrJob.filter(created_at__gte=today_start, created_at__lte=today_end)
            today_ocr_jobs = [
                job for job in today_ocr_jobs if job.status in [*OCR_SUCCESS_STATUSES, *OCR_FAILURE_STATUSES]
            ]
            today_ocr_total = len(today_ocr_jobs)
            today_success_ocr = len([job for job in today_ocr_jobs if job.status in OCR_SUCCESS_STATUSES])
            ocr_success_rate = (today_success_ocr / today_ocr_total * 100) if today_ocr_total > 0 else 0

            yesterday_ocr_jobs = await OcrJob.filter(created_at__gte=yesterday_start, created_at__lte=yesterday_end)
            yesterday_ocr_jobs = [
                job for job in yesterday_ocr_jobs if job.status in [*OCR_SUCCESS_STATUSES, *OCR_FAILURE_STATUSES]
            ]
            yesterday_ocr_total = len(yesterday_ocr_jobs)
            yesterday_success_ocr = len([job for job in yesterday_ocr_jobs if job.status in OCR_SUCCESS_STATUSES])
            yesterday_ocr_rate = (yesterday_success_ocr / yesterday_ocr_total * 100) if yesterday_ocr_total > 0 else 0
        except Exception:
            logger.exception("failed to build OCR success rates")
            ocr_success_rate = 0.0
            yesterday_ocr_rate = 0.0
        return ocr_success_rate, yesterday_ocr_rate

    @staticmethod
    async def _get_chatbot_counts(
        today_start: datetime,
        today_end: datetime,
        yesterday_start: datetime,
        yesterday_end: datetime,
    ) -> tuple[int, int]:
        try:
            today_chatbot = await ChatSession.filter(created_at__gte=today_start, created_at__lte=today_end).count()
            yesterday_chatbot = await ChatSession.filter(
                created_at__gte=yesterday_start, created_at__lte=yesterday_end
            ).count()
        except Exception:
            logger.exception("failed to build chatbot counts")
            today_chatbot = 0
            yesterday_chatbot = 0
        return today_chatbot, yesterday_chatbot

    @staticmethod
    async def _get_system_errors(
        today_start: datetime,
        today_end: datetime,
        yesterday_start: datetime,
        yesterday_end: datetime,
    ) -> tuple[int, float]:
        try:
            today_failed_ocr = await OcrJob.filter(
                created_at__gte=today_start,
                created_at__lte=today_end,
                status__in=OCR_FAILURE_STATUSES,
            ).count()
            yesterday_failed_ocr = await OcrJob.filter(
                created_at__gte=yesterday_start,
                created_at__lte=yesterday_end,
                status__in=OCR_FAILURE_STATUSES,
            ).count()

            today_failed_guides = await Guide.filter(
                created_at__gte=today_start,
                created_at__lte=today_end,
                status=GuideStatus.FAILED,
            ).count()
            yesterday_failed_guides = await Guide.filter(
                created_at__gte=yesterday_start,
                created_at__lte=yesterday_end,
                status=GuideStatus.FAILED,
            ).count()

            system_errors = today_failed_ocr + today_failed_guides
            yesterday_errors = yesterday_failed_ocr + yesterday_failed_guides
            system_errors_change = (
                ((system_errors - yesterday_errors) / yesterday_errors * 100) if yesterday_errors > 0 else 0
            )
        except Exception:
            logger.exception("failed to build system error counts")
            system_errors = 0
            system_errors_change = 0
        return system_errors, system_errors_change

    @staticmethod
    async def _build_guide_trend(period_start: date, period_days: int) -> list[ChartDataPoint]:
        guide_trend: list[ChartDataPoint] = []
        for i in range(period_days):
            target_date = period_start + timedelta(days=i)
            target_start = datetime.combine(target_date, datetime.min.time())
            target_end = datetime.combine(target_date, datetime.max.time())

            try:
                count = await Guide.filter(created_at__gte=target_start, created_at__lte=target_end).count()
            except Exception:
                logger.exception("failed to build guide trend for date=%s", target_date)
                count = 0

            guide_trend.append(ChartDataPoint(date=target_date, value=count))
        return guide_trend

    @staticmethod
    async def _build_chatbot_trend(period_start: date, period_days: int) -> list[ChartDataPoint]:
        chatbot_trend: list[ChartDataPoint] = []
        for i in range(period_days):
            target_date = period_start + timedelta(days=i)
            target_start = datetime.combine(target_date, datetime.min.time())
            target_end = datetime.combine(target_date, datetime.max.time())
            try:
                count = await ChatSession.filter(created_at__gte=target_start, created_at__lte=target_end).count()
            except Exception:
                logger.exception("failed to build chatbot trend for date=%s", target_date)
                count = 0
            chatbot_trend.append(ChartDataPoint(date=target_date, value=count))
        return chatbot_trend

    @staticmethod
    async def _build_ocr_analysis() -> OCRAnalysis:
        try:
            all_ocr_jobs = await OcrJob.filter(status__in=[*OCR_SUCCESS_STATUSES, *OCR_FAILURE_STATUSES])
            total_processed = len(all_ocr_jobs)
            success_count = len([job for job in all_ocr_jobs if job.status in OCR_SUCCESS_STATUSES])
            failure_count = len([job for job in all_ocr_jobs if job.status in OCR_FAILURE_STATUSES])
            success_rate = (success_count / total_processed * 100) if total_processed > 0 else 0

            failed_jobs = [job for job in all_ocr_jobs if job.status in OCR_FAILURE_STATUSES]
            failure_reasons: dict[str, int] = {}
            for job in failed_jobs:
                reason = str(getattr(job, "error_message", "") or "").strip() or "알 수 없는 오류"
                lowered_reason = reason.casefold()
                if "해상도" in reason or "resolution" in lowered_reason:
                    reason = "이미지 해상도 부족"
                elif "텍스트" in reason or "text" in lowered_reason:
                    reason = "텍스트 인식 실패"
                elif "형식" in reason or "format" in lowered_reason:
                    reason = "이미지 형식 미지원"
                else:
                    reason = "기타 오류"
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

            top_failures = sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:3]
            if not top_failures:
                top_failures = [
                    ("이미지 해상도 부족", 0),
                    ("텍스트 인식 실패", 0),
                    ("이미지 형식 미지원", 0),
                ]
        except Exception:
            logger.exception("failed to build OCR analysis")
            total_processed = 0
            success_count = 0
            failure_count = 0
            success_rate = 0.0
            top_failures = [
                ("이미지 해상도 부족", 0),
                ("텍스트 인식 실패", 0),
                ("이미지 형식 미지원", 0),
            ]

        return OCRAnalysis(
            total_processed=total_processed,
            success_count=success_count,
            failure_count=failure_count,
            success_rate=round(success_rate, 1),
            top_failures=top_failures,
        )
