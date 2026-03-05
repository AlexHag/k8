from dotenv import load_dotenv
load_dotenv()

import logging

from flask import Flask
from flask_cors import CORS
from flask_sock import Sock

from config import CORS_ORIGINS
from database import create_engine_from_config, create_scoped_session, check_migration_version
from repositories import SessionRepository, MessageRepository
from services import SessionService
from routes import register_api_routes, register_ws_routes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app, origins=CORS_ORIGINS)
    sock = Sock(app)

    engine = create_engine_from_config()
    check_migration_version(engine)

    db_session = create_scoped_session(engine)

    session_repo = SessionRepository(db_session)
    message_repo = MessageRepository(db_session)
    session_service = SessionService(session_repo, message_repo)

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    register_api_routes(app, session_service)
    register_ws_routes(sock, session_service)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
