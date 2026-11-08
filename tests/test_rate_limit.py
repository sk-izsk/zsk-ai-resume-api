import asyncio
import unittest

from app import rate_limit
from app.config import Settings
from app.rate_limit import reserve_request, settle_request


def make_settings(**overrides):
    values = {
        "GROQ_API_KEY": "test",
        "UPSTASH_REDIS_REST_URL": "https://example.com",
        "UPSTASH_REDIS_REST_TOKEN": "test",
        "PORTFOLIO_PROFILE_URL": "https://example.com/profile.json",
        "RATE_LIMIT_MAX_REQUESTS": 3,
        "RATE_LIMIT_MAX_REFUSALS": 10,
        "RATE_LIMIT_WINDOW_SECONDS": 3600,
        "RATE_LIMIT_ENABLED": True,
    }
    return Settings(**{**values, **overrides})


class FakeRedis:
    """Enough of Redis for the limiter, with a yield before each reply so parallel requests interleave."""

    def __init__(self):
        self.values: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def command(self, name, *parts):
        await asyncio.sleep(0)
        key = parts[0]
        if name == "INCR":
            self.values[key] = self.values.get(key, 0) + 1
            return self.values[key]
        if name == "DECR":
            self.values[key] = self.values.get(key, 0) - 1
            return self.values[key]
        if name == "DEL":
            self.values.pop(key, None)
            self.ttls.pop(key, None)
            return 1
        if name == "GET":
            return str(self.values[key]) if key in self.values else None
        if name == "EXPIRE":
            self.ttls[key] = int(parts[1])
            return 1
        if name == "TTL":
            return self.ttls.get(key, -2)
        if name == "SET":
            return "OK"
        raise AssertionError(f"Unexpected command: {name}")


class DownRedis:
    async def command(self, *parts):
        raise ConnectionError("redis host not found")


async def ask(redis, settings, outcome, ip="127.0.0.1"):
    state = await reserve_request(redis, settings, ip)
    if not state.allowed:
        return state
    return await settle_request(redis, settings, ip, outcome)


class RateLimitTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        rate_limit._local.clear()

    async def test_three_answers_then_blocked(self):
        settings, redis = make_settings(), FakeRedis()

        remaining = [(await ask(redis, settings, "answer")).remaining for _ in range(3)]
        fourth = await reserve_request(redis, settings, "127.0.0.1")

        self.assertEqual(remaining, [2, 1, 0])
        self.assertFalse(fourth.allowed)
        self.assertEqual(fourth.reset_in_seconds, 3600)

    async def test_refusals_and_failures_leave_answers_alone(self):
        settings, redis = make_settings(), FakeRedis()

        await ask(redis, settings, "refusal")
        await ask(redis, settings, "failed")
        state = await ask(redis, settings, "answer")

        self.assertEqual(state.remaining, 2)
        self.assertEqual(redis.values, {"rate:127.0.0.1": 1, "rate-refusal:127.0.0.1": 1})

    async def test_refusals_have_their_own_higher_cap(self):
        settings, redis = make_settings(RATE_LIMIT_MAX_REFUSALS=10), FakeRedis()

        for _ in range(10):
            self.assertTrue((await ask(redis, settings, "refusal")).remaining == 3)
        eleventh = await reserve_request(redis, settings, "127.0.0.1")

        self.assertFalse(eleventh.allowed)
        self.assertEqual(eleventh.remaining, 3)

    async def test_a_parallel_burst_cannot_pass_the_limit(self):
        settings, redis = make_settings(), FakeRedis()

        states = await asyncio.gather(*[reserve_request(redis, settings, "127.0.0.1") for _ in range(8)])

        self.assertEqual(sum(state.allowed for state in states), 3)
        self.assertEqual(redis.values["rate:127.0.0.1"], 3)

    async def test_a_burst_gets_every_free_slot_when_both_caps_match(self):
        settings, redis = make_settings(RATE_LIMIT_MAX_REFUSALS=3), FakeRedis()

        states = await asyncio.gather(*[reserve_request(redis, settings, "127.0.0.1") for _ in range(6)])

        self.assertEqual(sum(state.allowed for state in states), 3)

    async def test_can_disable_rate_limit_for_local_development(self):
        settings, redis = make_settings(RATE_LIMIT_ENABLED=False), FakeRedis()

        result = await reserve_request(redis, settings, "127.0.0.1")

        self.assertTrue(result.allowed)
        self.assertEqual(result.remaining, 3)
        self.assertEqual(redis.values, {})

    async def test_falls_back_to_memory_when_redis_is_down(self):
        settings, redis = make_settings(RATE_LIMIT_MAX_REQUESTS=2), DownRedis()

        await ask(redis, settings, "answer", "10.0.0.9")
        await ask(redis, settings, "refusal", "10.0.0.9")
        await ask(redis, settings, "answer", "10.0.0.9")
        third = await reserve_request(redis, settings, "10.0.0.9")

        self.assertFalse(third.allowed)
        self.assertGreater(third.reset_in_seconds, 0)


if __name__ == "__main__":
    unittest.main()
