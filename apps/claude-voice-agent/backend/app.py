import logging

from flask import Flask
from flask_cors import CORS
from flask_sock import Sock

from config import CORS_ORIGINS, DATABASE_PATH
from repositories.sqlite import (
    SQLiteConnectionManager,
    SQLiteSessionRepository,
    SQLiteMessageRepository,
)
from services import SessionService
from routes import register_api_routes, register_ws_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, origins=CORS_ORIGINS)
    sock = Sock(app)

    db = SQLiteConnectionManager(DATABASE_PATH)
    db.init_db()

    session_repo = SQLiteSessionRepository(db)
    message_repo = SQLiteMessageRepository(db)
    session_service = SessionService(session_repo, message_repo)

    register_api_routes(app, session_service)
    register_ws_routes(sock, session_service)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
