from fastapi import WebSocket

from app.database.schemas.Scan import ScanEventType


class ConnectionManager:
    """Manages WebSocket connections for scan and chat updates."""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, scan_id: str):
        await websocket.accept()
        if scan_id not in self.active_connections:
            self.active_connections[scan_id] = []
        self.active_connections[scan_id].append(websocket)

    def disconnect(self, websocket: WebSocket, scan_id: str):
        if scan_id in self.active_connections:
            if websocket in self.active_connections[scan_id]:
                self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]

    async def send_to_scan(self, scan_id: str, message: dict):
        if scan_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            for conn in disconnected:
                self.disconnect(conn, scan_id)

    async def send_scan_event(self, scan_id: str, event_type: str, payload: dict):
        await self.send_to_scan(
            scan_id=scan_id,
            message={
                "type": ScanEventType.SCAN_STATUS.value,
                "event": event_type,
                "payload": payload,
            },
        )

    async def stream_chat_chunk(
        self, scan_id: str, chunk: str, is_complete: bool = False
    ) -> None:
        await self.send_to_scan(
            scan_id=scan_id,
            message={
                "type": ScanEventType.CHAT_CHUNK.value,
                "chunk": chunk,
                "is_complete": is_complete,
            },
        )


manager = ConnectionManager()
