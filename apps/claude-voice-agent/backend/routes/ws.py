from __future__ import annotations

import logging

from flask import request
from flask_sock import Sock

from services.session_service import SessionService
from services.redis_consumer import ConnectionRegistry
from services.tts import ws_send

logger = logging.getLogger(__name__)


def register_ws_routes(
    sock: Sock,
    session_service: SessionService,
    registry: ConnectionRegistry,
) -> None:
    @sock.route("/ws")
    def websocket_handler(ws):
        session_id = request.args.get("session_id")
        if not session_id:
            ws_send(ws, {"type": "error", "message": "session_id is required"})
            return

        session = session_service.get_session(session_id)
        if not session:
            ws_send(ws, {"type": "error", "message": "Session not found"})
            return

        registry.register(session_id, ws)
        logger.info(
            "WebSocket connected for session %s (mode=%s)", session_id, session.mode
        )

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    logger.info(
                        "session=%s WS received None (client disconnected)",
                        session_id,
                    )
                    break
        except Exception:
            logger.info("WebSocket disconnected for session %s", session_id)
        finally:
            registry.unregister(session_id)
