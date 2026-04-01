from fastapi import APIRouter, Depends

from app.apis.v1.auth_routers import auth_router
from app.apis.v1.chat_routers import chat_router
from app.apis.v1.dashboard_routers import dashboard_router
from app.apis.v1.document_routers import document_router
from app.apis.v1.guide_routers import guide_router
from app.apis.v1.hospital_calendar_api import router as hospital_calendar_router
from app.apis.v1.invitation_routers import invitation_router
from app.apis.v1.medication_intake_api import router as medication_router
from app.apis.v1.notification_routers import notification_router
from app.apis.v1.patient_profile_routers import router as patient_profile_router
from app.apis.v1.public_routers import public_router
from app.apis.v1.settings_routers import router as settings_router
from app.apis.v1.user_routers import user_router
from app.dependencies.security import get_request_user

v1_routers = APIRouter(prefix="/api/v1")
v1_routers.include_router(auth_router)
v1_routers.include_router(public_router)
v1_routers.include_router(user_router)
v1_routers.include_router(invitation_router)
v1_routers.include_router(patient_profile_router)
v1_routers.include_router(notification_router, dependencies=[Depends(get_request_user)])
v1_routers.include_router(dashboard_router, dependencies=[Depends(get_request_user)])
v1_routers.include_router(document_router)
v1_routers.include_router(medication_router)
v1_routers.include_router(hospital_calendar_router)
v1_routers.include_router(settings_router)
v1_routers.include_router(guide_router)
v1_routers.include_router(chat_router)
