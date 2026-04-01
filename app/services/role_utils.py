from tortoise.expressions import Q

from app.models.healthcare import UserRole


async def user_has_role(user_id: int, *roles: str) -> bool:
    normalized_roles = [role.strip().upper() for role in roles if role and role.strip()]
    if not normalized_roles:
        return False

    return await (
        UserRole.filter(user_id=user_id)
        .filter(Q(role__name__in=normalized_roles) | Q(role__code__in=normalized_roles))
        .exists()
    )
