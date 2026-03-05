from __future__ import annotations

import base64
import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor, Future

from openai import OpenAI
from simple_websocket import ConnectionClosed

from config import TTS_MODEL, VOICE

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_TTS_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tts")


class WsClosed(Exception):
    """The WebSocket connection was closed while we were streaming."""


def ws_send(ws, payload: dict) -> None:
    """Send a JSON payload; converts ConnectionClosed to WsClosed."""
    try:
        ws.send(json.dumps(payload))
    except ConnectionClosed:
        raise WsClosed()


def tts_fetch(text: str, openai_client: OpenAI) -> bytes:
    """Fetch the full PCM audio for a sentence and return it as raw bytes."""
    response = openai_client.audio.speech.create(
        model=TTS_MODEL, voice=VOICE, input=text, response_format="pcm"
    )
    return response.read()


def process_text_block(ws, text: str, openai_client: OpenAI) -> None:
    """Convert a text block to speech and stream audio to the WebSocket.

    All per-sentence TTS requests are dispatched concurrently via a shared
    thread-pool. Audio is then streamed to the client in sentence order so
    playback remains coherent, while later sentences are already being fetched
    in the background.

    Raises WsClosed if the connection drops mid-stream.
    """
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        return

    futures: list[Future[bytes]] = [
        _TTS_EXECUTOR.submit(tts_fetch, sentence, openai_client)
        for sentence in sentences
    ]

    for sentence, future in zip(sentences, futures):
        ws_send(ws, {"type": "audio_delta", "transcript": sentence + " "})
        audio_data = future.result()
        for i in range(0, len(audio_data), 4096):
            ws_send(
                ws,
                {
                    "type": "audio_delta",
                    "data": base64.b64encode(audio_data[i : i + 4096]).decode(),
                },
            )
