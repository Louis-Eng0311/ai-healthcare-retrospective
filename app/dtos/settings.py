from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    dark_mode: bool = Field(default=False, description="다크 모드")
    language: str = Field(default="ko", description="언어 설정")
    push_notifications: bool = Field(default=True, description="알림 설정")


class UserSettingsUpdateRequest(BaseModel):
    dark_mode: bool | None = Field(default=None, description="다크 모드")
    language: str | None = Field(default=None, description="언어 설정")
    push_notifications: bool | None = Field(default=None, description="알림 설정")
