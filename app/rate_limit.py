"""Per-IP limits: a few real answers per window, and a higher cap on off-topic refusals.

Every request reserves one slot in both counters before the AI is called, using atomic INCR, so a
burst of parallel requests can never get past a limit. Once the reply is known, the slot it didn't
use is handed back with DECR: an answer keeps its answer slot, a refusal keeps its refusal slot,
and a failure keeps neither.
"""

import logging
import time
from typing import Literal

from app.config import Settings
from app.redis_client import RedisClient
from app.schemas import RateLimitState

logger = logging.getLogger(__name__)

Outcome = Literal["answer", "refusal", "failed"]

# ponytail: per-process fallback used only while Redis is unreachable; it resets on restart
# and isn't shared between instances, which is fine for one Render instance.
_local: dict[str, tuple[int, float]] = {}


def _answer_key(ip: str) -> str:
    return f"rate:{ip}"


def _refusal_key(ip: str) -> str:
    return f"rate-refusal:{ip}"


def _local_read(key: str) -> tuple[int, int]:
    count, expires_at = _local.get(key, (0, 0.0))
    left = expires_at - time.monotonic()
    return (count, int(left)) if left > 0 and count > 0 else (0, 0)


async def _incr(redis: RedisClient, key: str, window: int) -> tuple[int, int]:
    try:
        count = int(await redis.command("INCR", key))
        if count == 1:
            await redis.command("EXPIRE", key, window)
        return count, int(await redis.command("TTL", key))
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        count, ttl = _local_read(key)
        ttl = ttl or window
        _local[key] = (count + 1, time.monotonic() + ttl)
        return count + 1, ttl


async def _decr(redis: RedisClient, key: str) -> None:
    try:
        # A key that expired mid-request would go negative and lose its TTL, so drop it instead.
        if int(await redis.command("DECR", key)) <= 0:
            await redis.command("DEL", key)
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        count, ttl = _local_read(key)
        _local[key] = (max(count - 1, 0), time.monotonic() + ttl)


async def _read(redis: RedisClient, key: str) -> tuple[int, int]:
    try:
        count = int(await redis.command("GET", key) or 0)
        return count, int(await redis.command("TTL", key)) if count else 0
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        return _local_read(key)


def _state(settings: Settings, answers: int, ttl: int, allowed: bool = True) -> RateLimitState:
    return RateLimitState(
        allowed=allowed,
        remaining=max(settings.rate_limit_max_requests - answers, 0),
        reset_in_seconds=max(ttl, 0),
    )


async def reserve_request(redis: RedisClient, settings: Settings, ip: str) -> RateLimitState:
    """Holds one answer slot and one refusal slot for this request, or refuses it if either is full."""
    if not settings.rate_limit_enabled:
        return _state(settings, 0, 0)

    window = settings.rate_limit_window_seconds
    answers, answer_ttl = await _incr(redis, _answer_key(ip), window)
    if answers > settings.rate_limit_max_requests:
        await _decr(redis, _answer_key(ip))
        return _state(settings, answers - 1, answer_ttl, allowed=False)

    # Taken only after the answer slot, so requests over the answer limit never crowd out refusal slots.
    refusals, refusal_ttl = await _incr(redis, _refusal_key(ip), window)
    if refusals > settings.rate_limit_max_refusals:
        await _decr(redis, _refusal_key(ip))
        await _decr(redis, _answer_key(ip))
        return _state(settings, answers - 1, refusal_ttl, allowed=False)

    return _state(settings, answers, answer_ttl)


async def settle_request(redis: RedisClient, settings: Settings, ip: str, outcome: Outcome) -> RateLimitState:
    """Hands back the slots this request didn't use, and returns what the visitor has left."""
    if not settings.rate_limit_enabled:
        return _state(settings, 0, 0)

    if outcome != "answer":
        await _decr(redis, _answer_key(ip))
    if outcome != "refusal":
        await _decr(redis, _refusal_key(ip))

    answers, ttl = await _read(redis, _answer_key(ip))
    return _state(settings, answers, ttl)
