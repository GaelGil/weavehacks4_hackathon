from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket.ConnectionManager import manager

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/scans/{scan_id}")
async def scan_websocket(websocket: WebSocket, scan_id: str):
    await manager.connect(websocket, scan_id)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, scan_id)
