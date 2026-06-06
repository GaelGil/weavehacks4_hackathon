from fastapi import APIRouter

from app.api.scamdetect.controller import router as scan_router
from app.api.utils.controller import router as utils_router
from app.api.websocket.controller import router as websocket_router

api_router = APIRouter()
api_router.include_router(scan_router)
api_router.include_router(utils_router)
api_router.include_router(websocket_router)
