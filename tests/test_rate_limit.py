import unittest

from app.config import Settings
from app.rate_limit import check_rate_limit


class FakeRedis:
    def __init__(self):
        self.count = 0
        self.ttl = -1

    async def command(self, name, *parts):
        if name == "INCR":
            self.count += 1
            return self.count
        if name == "EXPIRE":
            self.ttl = int(parts[1])
            return 1
        if name == "TTL":
            return self.ttl
        raise AssertionError(f"Unexpected command: {name}")


class RateLimitTest(unittest.IsolatedAsyncioTestCase):
    async def test_blocks_after_configured_limit(self):
        settings = Settings(
            GROQ_API_KEY="test",
            UPSTASH_REDIS_REST_URL="https://example.com",
            UPSTASH_REDIS_REST_TOKEN="test",
            PORTFOLIO_PROFILE_URL="https://example.com/profile.json",
            RATE_LIMIT_MAX_REQUESTS=3,
            RATE_LIMIT_WINDOW_SECONDS=3600,
            RATE_LIMIT_ENABLED=True,
        )
        redis = FakeRedis()

        first = await check_rate_limit(redis, settings, "127.0.0.1")
        second = await check_rate_limit(redis, settings, "127.0.0.1")
        third = await check_rate_limit(redis, settings, "127.0.0.1")
        fourth = await check_rate_limit(redis, settings, "127.0.0.1")

        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)
        self.assertTrue(third.allowed)
        self.assertFalse(fourth.allowed)
        self.assertEqual(fourth.remaining, 0)
        self.assertEqual(fourth.reset_in_seconds, 3600)

    async def test_can_disable_rate_limit_for_local_development(self):
        settings = Settings(
            GROQ_API_KEY="test",
            UPSTASH_REDIS_REST_URL="https://example.com",
            UPSTASH_REDIS_REST_TOKEN="test",
            PORTFOLIO_PROFILE_URL="https://example.com/profile.json",
            RATE_LIMIT_ENABLED=False,
        )

        result = await check_rate_limit(FakeRedis(), settings, "127.0.0.1")

        self.assertTrue(result.allowed)
        self.assertEqual(result.remaining, 3)
        self.assertEqual(result.reset_in_seconds, 0)


if __name__ == "__main__":
    unittest.main()
