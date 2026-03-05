import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import logging
import threading

from flask import Flask
from flask_cors import CORS
from flask_sock import Sock
from openai import OpenAI

from config import CORS_ORIGINS, REDIS_URL, OPENAI_API_KEY
from database import create_engine_from_config, create_scoped_session, check_migration_version
from common.redis_streams import RedisStreamClient
from repositories import SessionRepository, MessageRepository
from services import SessionService
from services.redis_consumer import ConnectionRegistry, BackendRedisConsumer
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

    redis_client = RedisStreamClient(REDIS_URL)
    registry = ConnectionRegistry()
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

    consumer = BackendRedisConsumer(
        redis_client=redis_client,
        session_service=session_service,
        openai_client=openai_client,
        registry=registry,
    )
    consumer_thread = threading.Thread(
        target=consumer.run, daemon=True, name="redis-consumer"
    )
    consumer_thread.start()
    logger.info("Backend Redis consumer thread started")

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session.remove()

    register_api_routes(app, session_service)
    register_ws_routes(sock, session_service, redis_client, registry)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
