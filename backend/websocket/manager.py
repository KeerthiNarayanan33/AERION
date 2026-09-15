import asyncio
import json
from typing import List, Dict, Any
from fastapi import WebSocket
from backend.logger import logger

class ConnectionManager:
    """Manages real-time WebSocket clients connected to the surveillance dashboard."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Active connections: {len(self.active_connections)}")

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, data: Dict[str, Any]):
        """Broadcasts a JSON-serializable dictionary to all active clients."""
        if not self.active_connections:
            return

        message = json.dumps(data)
        async with self._lock:
            disconnected_sockets = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.warning(f"Error sending message to client: {e}. Marking for removal.")
                    disconnected_sockets.append(connection)

            for dead_ws in disconnected_sockets:
                if dead_ws in self.active_connections:
                    self.active_connections.remove(dead_ws)

    def broadcast_sync(self, data: Dict[str, Any]):
        """Synchronous wrapper to safely schedule broadcast on the running event loop."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                asyncio.create_task(self.broadcast(data))
        except RuntimeError:
            pass

ws_manager = ConnectionManager()
