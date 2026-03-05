import os

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CLAUDE_CLI_PATH = os.environ.get(
    "CLAUDE_CLI_PATH", r"C:\Users\AlexHagdahl\.local\bin\claude.exe"
)
CLAUDE_CWD = os.environ.get("CLAUDE_CWD", os.path.dirname(os.path.abspath(__file__)))

CONSUMER_NAME = os.environ.get("CONSUMER_NAME", "agent-1")
