from datetime import date, datetime
from typing import Any

from pydantic import EmailStr

from app.core import config
from app.models.users import Gender, User

ALLOWED_UPDATE_FIELDS = ["name", "email", "phone_number", "gender", "birthday"]
UPDATED_AT_FIELD = "updated_at"


class UserRepository:
    def __init__(self):
        self._model = User

    async def get_all(self):
        return await self._model.all()

    async def get_user(self, user_id: int) -> User | None:
        return await self._model.get_or_none(id=user_id)

    async def create_user(
        self,
        email: str | EmailStr,
        hashed_password: str | None,
        name: str,
        phone_number: str,
        gender: Gender,
        birthday: date,
        *,
        is_active: bool = True,
    ) -> User:
        return await self._model.create(
            email=email,
            hashed_password=hashed_password,
            name=name,
            phone_number=phone_number,
            gender=gender,
            birthday=birthday,
            is_active=is_active,
        )

    async def get_user_by_email(self, email: str) -> User | None:
        return await self._model.get_or_none(email=email)

    async def exists_by_email(self, email: str, *, exclude_user_id: int | None = None) -> bool:
        qs = self._model.filter(email=email)
        if exclude_user_id is not None:
            qs = qs.exclude(id=exclude_user_id)
        return await qs.exists()

    async def exists_by_phone_number(self, phone_number: str, *, exclude_user_id: int | None = None) -> bool:
        qs = self._model.filter(phone_number=phone_number)
        if exclude_user_id is not None:
            qs = qs.exclude(id=exclude_user_id)
        return await qs.exists()

    async def update_instance(self, user: User, data: dict[str, Any]) -> None:
        update_fields = []
        for key, value in data.items():
            if value is not None and key in ALLOWED_UPDATE_FIELDS:
                setattr(user, key, value)
                update_fields.append(key)
        if update_fields:
            user.updated_at = datetime.now(config.TIMEZONE)
            update_fields.append(UPDATED_AT_FIELD)
            await user.save(update_fields=update_fields)

    async def get_user_by_name_and_phone(self, name: str, phone_number: str) -> User | None:
        return await self._model.get_or_none(name=name, phone_number=phone_number)

    async def get_user_by_email_name_phone(self, email: str, name: str, phone_number: str) -> User | None:
        return await self._model.get_or_none(email=email, name=name, phone_number=phone_number)
