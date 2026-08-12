from app.config import Settings
from app.redis_client import RedisClient
from app.schemas import RateLimitState


async def check_rate_limit(redis: RedisClient, settings: Settings, ip: str) -> RateLimitState:
    if not settings.rate_limit_enabled:
        return RateLimitState(
            allowed=True,
            remaining=settings.rate_limit_max_requests,
            reset_in_seconds=0,
        )

    key = f"rate:{ip}"
    count = int(await redis.command("INCR", key))

    if count == 1:
        await redis.command("EXPIRE", key, settings.rate_limit_window_seconds)

    ttl = int(await redis.command("TTL", key))
    reset_in_seconds = max(ttl, 0)
    remaining = max(settings.rate_limit_max_requests - count, 0)

    return RateLimitState(
        allowed=count <= settings.rate_limit_max_requests,
        remaining=remaining,
        reset_in_seconds=reset_in_seconds,
    )
