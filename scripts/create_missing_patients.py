"""기존 사용자들을 위한 Patient 레코드 생성 스크립트"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def create_missing_patients():
    """PATIENT 역할을 가진 사용자 중 Patient 레코드가 없는 경우 생성"""
    from tortoise import Tortoise

    from app.core.config import Config
    from app.models.healthcare import UserRole
    from app.models.patients import Patient

    config = Config()
    # Tortoise ORM 초기화
    db_url = f"mysql://{config.DB_USER}:{config.DB_PASSWORD}@{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"
    await Tortoise.init(
        db_url=db_url,
        modules={"models": ["app.models"]},
    )
    await Tortoise.generate_schemas()

    # PATIENT 역할을 가진 모든 사용자 조회
    patient_role_users = await UserRole.filter(role__name="PATIENT").select_related("user").all()

    created_count = 0
    for user_role in patient_role_users:
        user = user_role.user
        # Patient 레코드가 없으면 생성
        patient, created = await Patient.get_or_create(user_id=user.id, defaults={"display_name": user.name})
        if created:
            print(f"✓ Patient 레코드 생성: {user.name} (user_id={user.id})")
            created_count += 1
        else:
            print(f"- Patient 레코드 이미 존재: {user.name} (user_id={user.id})")

    print(f"\n총 {created_count}개의 Patient 레코드가 생성되었습니다.")

    await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(create_missing_patients())
