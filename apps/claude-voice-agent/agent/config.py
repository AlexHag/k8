import os
import uuid

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CLAUDE_CLI_PATH = os.environ.get(
    "CLAUDE_CLI_PATH", r"C:\Users\AlexHagdahl\.local\bin\claude.exe"
)
CLAUDE_CWD = os.environ.get("CLAUDE_CWD", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

POD_ID = os.environ.get("HOSTNAME", str(uuid.uuid4()))
HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL", "30"))
HEARTBEAT_INTERVAL = int(os.environ.get("HEARTBEAT_INTERVAL", "10"))
