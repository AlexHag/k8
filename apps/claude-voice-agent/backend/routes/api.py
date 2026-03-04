from __future__ import annotations

from flask import Flask, request, jsonify

from services.session_service import SessionService


def register_api_routes(app: Flask, session_service: SessionService) -> None:
    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.route("/api/sessions", methods=["POST"])
    def create_session():
        data = request.get_json()
        if not data or "title" not in data or "mode" not in data:
            return jsonify({"error": "title and mode are required"}), 400
        if data["mode"] not in ("openai", "claude_code"):
            return jsonify({"error": "mode must be 'openai' or 'claude_code'"}), 400
        session = session_service.create_session(data["title"], data["mode"])
        return jsonify(session.to_dict()), 201

    @app.route("/api/sessions", methods=["GET"])
    def list_sessions():
        sessions = session_service.list_sessions()
        return jsonify([s.to_dict() for s in sessions])

    @app.route("/api/sessions/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        result = session_service.get_session_with_messages(session_id)
        if result is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(result)

    @app.route("/api/sessions/<session_id>", methods=["PATCH"])
    def update_session(session_id: str):
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"error": "title is required"}), 400
        session = session_service.update_session_title(session_id, data["title"])
        if session is None:
            return jsonify({"error": "Not found"}), 404
        return jsonify(session.to_dict())

    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def delete_session(session_id: str):
        success = session_service.delete_session(session_id)
        if not success:
            return jsonify({"error": "Not found"}), 404
        return "", 204
