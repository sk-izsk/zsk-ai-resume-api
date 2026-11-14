"""Per-IP limits: a few replies per window (answers and off-topic refusals both count).

Every request reserves one slot in both counters before the AI is called, using atomic INCR, so a
burst of parallel requests can never get past a limit. Once the reply is known, the slot it didn't
use is handed back with DECR: an answer or a refusal keeps its answer slot, and a failure keeps neither.
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


def _local_add(key: str, change: int, window: int) -> int:
    count, ttl = _local_read(key)
    count = max(count + change, 0)
    _local[key] = (count, time.monotonic() + (ttl or window))
    return count


async def _incr(redis: RedisClient, key: str, window: int) -> tuple[int, int]:
    try:
        count, ttl = await redis.pipeline(["INCR", key], ["TTL", key])
        if int(ttl) < 0:
            await redis.command("EXPIRE", key, window)
            ttl = window
        return int(count), int(ttl)
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        return _local_add(key, 1, window), _local_read(key)[1]


async def _release(redis: RedisClient, keys: list[str], read_key: str) -> tuple[int, int]:
    """DECR each key and read read_key's count and TTL, all in one round trip."""
    try:
        *counts, value, ttl = await redis.pipeline(
            *[["DECR", key] for key in keys], ["GET", read_key], ["TTL", read_key]
        )
        # A key that expired mid-request would go negative and lose its TTL, so drop it instead.
        emptied = [key for key, count in zip(keys, counts) if int(count) <= 0]
        if emptied:
            await redis.command("DEL", *emptied)
        count = max(int(value or 0), 0)
        return count, int(ttl) if count else 0
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        for key in keys:
            _local_add(key, -1, 0)
        return _local_read(read_key)


def _state(settings: Settings, answers: int, ttl: int, allowed: bool = True) -> RateLimitState:
    return RateLimitState(
        allowed=allowed,
        remaining=max(settings.rate_limit_max_requests - answers, 0),
        reset_in_seconds=max(ttl, 0),
    )


async def peek_usage(redis: RedisClient, settings: Settings, ip: str) -> RateLimitState:
    """What this IP has left, without using anything. Lets the site show the right count on open."""
    if not settings.rate_limit_enabled:
        return _state(settings, 0, 0)

    try:
        answers, answer_ttl, refusals = await redis.pipeline(
            ["GET", _answer_key(ip)], ["TTL", _answer_key(ip)], ["GET", _refusal_key(ip)]
        )
        answers, refusals = int(answers or 0), int(refusals or 0)
        answer_ttl = int(answer_ttl) if answers else 0
    except Exception as error:
        logger.warning("Redis rate limit failed, using in-memory limit: %s", error)
        answers, answer_ttl = _local_read(_answer_key(ip))
        refusals = _local_read(_refusal_key(ip))[0]

    allowed = answers < settings.rate_limit_max_requests and refusals < settings.rate_limit_max_refusals
    return _state(settings, answers, answer_ttl, allowed=allowed)


async def reserve_request(redis: RedisClient, settings: Settings, ip: str) -> RateLimitState:
    """Holds one answer slot and one refusal slot for this request, or refuses it if either is full."""
    if not settings.rate_limit_enabled:
        return _state(settings, 0, 0)

    window = settings.rate_limit_window_seconds
    answers, answer_ttl = await _incr(redis, _answer_key(ip), window)
    if answers > settings.rate_limit_max_requests:
        await _release(redis, [_answer_key(ip)], _answer_key(ip))
        return _state(settings, answers - 1, answer_ttl, allowed=False)

    # Taken only after the answer slot, so requests over the answer limit never crowd out refusal slots.
    refusals, refusal_ttl = await _incr(redis, _refusal_key(ip), window)
    if refusals > settings.rate_limit_max_refusals:
        await _release(redis, [_refusal_key(ip), _answer_key(ip)], _answer_key(ip))
        return _state(settings, answers - 1, refusal_ttl, allowed=False)

    return _state(settings, answers, answer_ttl)


async def settle_request(redis: RedisClient, settings: Settings, ip: str, outcome: Outcome) -> RateLimitState:
    """Hands back the slots this request didn't use, and returns what the visitor has left."""
    if not settings.rate_limit_enabled:
        return _state(settings, 0, 0)

    unused = {
        "answer": [_refusal_key(ip)],
        # ponytail: a refusal is a real LLM reply, so it uses an attempt like an answer; the refusal cap
        # is now unreachable below the answer limit, remove it if you don't plan to raise the caps.
        "refusal": [_refusal_key(ip)],
        "failed": [_answer_key(ip), _refusal_key(ip)],
    }[outcome]
    answers, ttl = await _release(redis, unused, _answer_key(ip))
    return _state(settings, answers, ttl)
