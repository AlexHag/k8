from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.redis_streams import RedisStreamClient
from consumer import AgentConsumer
from config import REDIS_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_consumer: AgentConsumer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer
    redis_client = RedisStreamClient(REDIS_URL)
    _consumer = AgentConsumer(redis_client)

    task = asyncio.create_task(_consumer.start())
    logger.info("Agent consumer task launched")

    yield

    _consumer.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    redis_client.close()
    logger.info("Agent shutdown complete")


app = FastAPI(title="Claude Agent Worker", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}
