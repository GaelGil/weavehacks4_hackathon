from fastapi import WebSocket

from app.database.schemas.Translation import TranslationResponseType


class ConnectionManager:
    """Manages WebSocket connections for message updates."""

    def __init__(self):
        # Map of translate_id -> list of connected WebSockets
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, translate_id: str):
        """
        Add a WebSocket connection to the manager.
        """
        # Accept the connection
        await websocket.accept()
        # Check if translate_id is in active_connections
        if translate_id not in self.active_connections:
            # If not, add it with an empty list
            self.active_connections[translate_id] = []
        # If translate_id is in active_connections, add the new connection
        self.active_connections[translate_id].append(websocket)

    def disconnect(self, websocket: WebSocket, translate_id: str):
        if translate_id in self.active_connections:
            if websocket in self.active_connections[translate_id]:
                self.active_connections[translate_id].remove(websocket)
            if not self.active_connections[translate_id]:
                del self.active_connections[translate_id]

    async def send_to_message(self, translate_id: str, message: dict):
        """Send message to all connections watching a specific message.

        Args:
            translate_id (str): Message ID
            message (dict): Message

        """
        if translate_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[translate_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            # Clean up disconnected
            for conn in disconnected:
                self.disconnect(conn, translate_id)

    async def stream_response_chunk(
        self,
        translate_id: str,
        chunk: str,
        is_complete: bool = False,
        msg_type: TranslationResponseType = TranslationResponseType.TRANSLATION_CHUNK,
    ):
        """Stream a response chunk to message connections.

        Args:
            translate_id (str): Message ID
            chunk (str): Response chunk
            is_complete (bool, optional): Whether the response is complete. Defaults to False.
            msg_type (str, optional): Message type. Defaults to "message_chunk".
        """
        await self.send_to_message(
            translate_id=translate_id,
            message={
                "type": msg_type.value,
                "chunk": chunk,
                "is_complete": is_complete,
            },
        )


manager = ConnectionManager()
