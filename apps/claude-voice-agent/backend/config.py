import os

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

MODEL = "gpt-4o-mini-audio-preview"
VOICE = "ash"
AUDIO_FORMAT = "pcm16"
TTS_MODEL = "tts-1"

DB_TYPE = os.environ.get("DB_TYPE", "sqlite")

_default_sqlite_url = "sqlite:///" + os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "voice_agent.db"
)
DATABASE_URL = os.environ.get("DATABASE_URL", _default_sqlite_url)

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]
