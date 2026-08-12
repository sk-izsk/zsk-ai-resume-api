import hashlib
import json

from app.redis_client import RedisClient
from app.schemas import ChatResponse


def cache_key(message: str, version: str) -> str:
    normalized = " ".join(message.lower().strip().split())
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"chat-cache:{version}:{digest}"


async def get_cached_answer(redis: RedisClient, message: str, version: str) -> ChatResponse | None:
    raw = await redis.command("GET", cache_key(message, version))
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
    await redis.command("SET", cache_key(message, version), json.dumps(response.model_dump()), "EX", ttl)
