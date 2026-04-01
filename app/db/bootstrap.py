from tortoise import Tortoise


async def _table_exists(table_name: str) -> bool:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        LIMIT 1
        """,
        [table_name],
    )
    return bool(rows)


async def _column_exists(table_name: str, column_name: str) -> bool:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
        LIMIT 1
        """,
        [table_name, column_name],
    )
    return bool(rows)


async def _unique_index_exists(table_name: str, column_name: str) -> bool:
    conn = Tortoise.get_connection("default")
    rows = await conn.execute_query_dict(
        """
        SELECT 1
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
          AND non_unique = 0
        LIMIT 1
        """,
        [table_name, column_name],
    )
    return bool(rows)


async def _safe_exec(sql: str) -> None:
    conn = Tortoise.get_connection("default")
    await conn.execute_script(sql)


async def ensure_users_schema_compatibility() -> None:
    if not await _table_exists("users"):
        return

    if await _column_exists("users", "hashed_password") and not await _column_exists("users", "password_hash"):
        await _safe_exec("ALTER TABLE users CHANGE COLUMN hashed_password password_hash VARCHAR(128) NULL;")

    if await _column_exists("users", "birthday") and not await _column_exists("users", "birth_date"):
        await _safe_exec("ALTER TABLE users CHANGE COLUMN birthday birth_date DATE NOT NULL;")

    if await _column_exists("users", "phone_number") and not await _column_exists("users", "phone"):
        await _safe_exec("ALTER TABLE users CHANGE COLUMN phone_number phone VARCHAR(20) NOT NULL;")

    if not await _column_exists("users", "nickname"):
        await _safe_exec("ALTER TABLE users ADD COLUMN nickname VARCHAR(50) NULL AFTER phone;")

    if not await _unique_index_exists("users", "email"):
        await _safe_exec("ALTER TABLE users ADD UNIQUE INDEX email (email);")

    if not await _unique_index_exists("users", "phone"):
        await _safe_exec("ALTER TABLE users ADD UNIQUE INDEX phone (phone);")


async def ensure_roles_schema_compatibility() -> None:
    if not await _table_exists("roles"):
        return

    if not await _column_exists("roles", "code"):
        await _safe_exec("ALTER TABLE roles ADD COLUMN code VARCHAR(30) NULL AFTER id;")
    await _safe_exec("UPDATE roles SET code = name WHERE code IS NULL OR code = '';")
    await _safe_exec("ALTER TABLE roles MODIFY COLUMN code VARCHAR(30) NOT NULL;")

    if not await _column_exists("roles", "description"):
        await _safe_exec("ALTER TABLE roles ADD COLUMN description VARCHAR(255) NULL AFTER name;")

    if not await _column_exists("roles", "created_at"):
        await _safe_exec("ALTER TABLE roles ADD COLUMN created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);")
    if not await _column_exists("roles", "updated_at"):
        await _safe_exec(
            "ALTER TABLE roles ADD COLUMN updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6);"
        )

    if not await _unique_index_exists("roles", "code"):
        await _safe_exec("ALTER TABLE roles ADD UNIQUE INDEX uid_roles_code (code);")


async def ensure_user_roles_schema_compatibility() -> None:
    if not await _table_exists("user_roles"):
        return

    if await _column_exists("user_roles", "created_at") and not await _column_exists("user_roles", "assigned_at"):
        await _safe_exec("ALTER TABLE user_roles CHANGE COLUMN created_at assigned_at DATETIME(6) NOT NULL;")

    if not await _column_exists("user_roles", "assigned_at"):
        await _safe_exec(
            "ALTER TABLE user_roles ADD COLUMN assigned_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6);"
        )


async def ensure_notification_settings_schema_compatibility() -> None:
    if not await _table_exists("notification_settings"):
        return

    if not await _column_exists("notification_settings", "hospital_schedule_reminder"):
        await _safe_exec(
            "ALTER TABLE notification_settings ADD COLUMN hospital_schedule_reminder BOOL NOT NULL DEFAULT 1;"
        )


async def _seed_admin_accounts() -> None:
    from app.models.domains.reference import Role, UserRole
    from app.models.users import User
    from app.utils.security import hash_password

    admin_role, _ = await Role.get_or_create(code="ADMIN", defaults={"name": "ADMIN"})

    admins = [
        {"email": "admin1@gmail.com", "name": "관리자1", "phone": "01000000001"},
        {"email": "admin2@gmail.com", "name": "관리자2", "phone": "01000000002"},
        {"email": "admin3@gmail.com", "name": "관리자3", "phone": "01000000003"},
        {"email": "admin4@gmail.com", "name": "관리자4", "phone": "01000000004"},
    ]
    from datetime import date

    for info in admins:
        if await User.filter(email=info["email"]).exists():
            continue
        if await User.filter(phone_number=info["phone"]).exists():
            continue
        user = await User.create(
            email=info["email"],
            hashed_password=hash_password("Admin1234!"),
            name=info["name"],
            phone_number=info["phone"],
            gender="MALE",
            birthday=date(1990, 1, 1),
        )
        await UserRole.get_or_create(user=user, role=admin_role)


async def bootstrap_database() -> None:
    await _seed_admin_accounts()
