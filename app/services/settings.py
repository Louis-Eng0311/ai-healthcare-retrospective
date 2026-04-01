from app.dtos.settings import UserSettingsResponse, UserSettingsUpdateRequest
from app.models.user_settings import UserSettings


class SettingsService:
    @staticmethod
    async def get_user_settings(user_id: int) -> UserSettingsResponse:
        settings = await UserSettings.filter(user_id=user_id).first()
        if not settings:
            settings = await UserSettings.create(user_id=user_id)

        return UserSettingsResponse(
            dark_mode=settings.dark_mode,
            language=settings.language,
            push_notifications=settings.push_notifications,
        )

    @staticmethod
    async def update_user_settings(user_id: int, request: UserSettingsUpdateRequest) -> UserSettingsResponse:
        settings = await UserSettings.filter(user_id=user_id).first()
        if not settings:
            settings = await UserSettings.create(user_id=user_id)

        if request.dark_mode is not None:
            settings.dark_mode = request.dark_mode
        if request.language is not None:
            settings.language = request.language
        if request.push_notifications is not None:
            settings.push_notifications = request.push_notifications

        await settings.save()

        return UserSettingsResponse(
            dark_mode=settings.dark_mode,
            language=settings.language,
            push_notifications=settings.push_notifications,
        )
