from fastapi import APIRouter
from fastapi.responses import ORJSONResponse

from app.models.healthcare import Role

public_router = APIRouter(prefix="/public", tags=["public"])


@public_router.get("/roles", response_class=ORJSONResponse)
async def list_roles() -> list[dict[str, str | None]]:
    roles = await Role.all().order_by("id")
    if not roles:
        return [
            {"code": "PATIENT", "name": "PATIENT", "description": "환자"},
            {"code": "CAREGIVER", "name": "CAREGIVER", "description": "보호자"},
            {"code": "ADMIN", "name": "ADMIN", "description": "관리자"},
        ]
    return [
        {
            "code": role.code,
            "name": role.name,
            "description": role.description,
        }
        for role in roles
    ]
