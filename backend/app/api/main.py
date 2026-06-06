from fastapi import APIRouter

from app.api.login.controller import router as login_router
from app.api.private.controller import router as private_router
from app.api.translation.controller import router as translation_router
from app.api.users.controller import router as users_router
from app.api.utils.controller import router as utils_router
from app.api.websocket.controller import router as websocket_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login_router)
api_router.include_router(users_router)
api_router.include_router(translation_router)
api_router.include_router(utils_router)
api_router.include_router(websocket_router)


if settings.ENVIRONMENT == "local":
    api_router.include_router(private_router)
