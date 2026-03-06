# ---------------------------------------------------------------------------
# Pod liveness
# ---------------------------------------------------------------------------
PODS_ALIVE_SET = "agent:pods:alive"


def pod_alive_key(pod_id: str) -> str:
    return f"agent:pods:{pod_id}:alive"


def pod_sessions_key(pod_id: str) -> str:
    return f"agent:pods:{pod_id}:sessions"


def pod_notify_key(pod_id: str) -> str:
    return f"agent:pods:{pod_id}:notify"


# ---------------------------------------------------------------------------
# Session keys
# ---------------------------------------------------------------------------
def session_pod_key(session_id: str) -> str:
    return f"agent:session:{session_id}:pod"


def session_prompt_stream(session_id: str) -> str:
    return f"agent:session:{session_id}:prompts"


def session_response_stream(session_id: str) -> str:
    return f"agent:session:{session_id}:responses"


# ---------------------------------------------------------------------------
# Consumer groups
# ---------------------------------------------------------------------------
PROMPT_CONSUMER_GROUP = "prompt-workers"
RESPONSE_CONSUMER_GROUP = "response-workers"
NOTIFY_CONSUMER_GROUP = "notify-workers"

# ---------------------------------------------------------------------------
# Heartbeat defaults (overridable via env vars in agent/config.py)
# ---------------------------------------------------------------------------
DEFAULT_HEARTBEAT_TTL = 30
DEFAULT_HEARTBEAT_INTERVAL = 10
