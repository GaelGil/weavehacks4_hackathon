from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket.ConnectionManager import manager

router = APIRouter(prefix="/ws", tags=["websocket"])


# Global connection manager instance


@router.websocket("/translate/{translation_id}")
async def message_websocket(websocket: WebSocket, translation_id: str):
    await manager.connect(websocket, translation_id)
    try:
        while True:
            # Keep connection alive, listen for any client messages
            _ = await websocket.receive_text()
            # Could handle client messages here if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket, translation_id)
