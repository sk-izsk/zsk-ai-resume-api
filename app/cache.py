import hashlib
import json
import logging

from app.redis_client import RedisClient
from app.schemas import ChatResponse

logger = logging.getLogger(__name__)


def cache_key(message: str, version: str) -> str:
    normalized = " ".join(message.lower().strip().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"chat-cache:{version}:{digest}"


async def get_cached_answer(redis: RedisClient, message: str, version: str) -> ChatResponse | None:
    # A cache outage only costs a fresh answer, so it never fails the request.
    try:
        raw = await redis.command("GET", cache_key(message, version))
    except Exception as error:
        logger.warning("Redis cache read failed: %s", error)
        return None
    if not raw:
        return None
    return ChatResponse.model_validate_json(raw)


async def set_cached_answer(
    redis: RedisClient,
    message: str,
    response: ChatResponse,
    ttl: int,
    version: str,
) -> None:
    try:
        await redis.command("SET", cache_key(message, version), json.dumps(response.model_dump()), "EX", ttl)
    except Exception as error:
        logger.warning("Redis cache write failed: %s", error)
