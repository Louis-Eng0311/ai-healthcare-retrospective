from datetime import date

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    total_users: int
    today_guides: int
    ocr_success_rate: float
    today_chatbot_requests: int
    system_errors: int
    total_users_change: float
    today_guides_change: float
    ocr_success_rate_change: float
    today_chatbot_requests_change: float
    system_errors_change: float


class ChartDataPoint(BaseModel):
    date: date
    value: int


class OCRAnalysis(BaseModel):
    total_processed: int
    success_count: int
    failure_count: int
    success_rate: float
    top_failures: list[tuple[str, int]]


class DashboardResponse(BaseModel):
    stats: DashboardStatsResponse
    guide_trend: list[ChartDataPoint]
    chatbot_trend: list[ChartDataPoint]
    ocr_analysis: OCRAnalysis
