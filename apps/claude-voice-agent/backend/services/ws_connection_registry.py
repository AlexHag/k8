import threading

class WsConnectionRegistry:
    """Thread-safe registry mapping session_id -> active WebSocket."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, object] = {}

    def register(self, session_id: str, ws) -> None:
        with self._lock:
            self._connections[session_id] = ws

    def unregister(self, session_id: str) -> None:
        with self._lock:
            self._connections.pop(session_id, None)

    def get(self, session_id: str):
        with self._lock:
            return self._connections.get(session_id)
