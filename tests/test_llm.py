import unittest
from unittest.mock import AsyncMock, patch

from app.config import Settings
from app.llm import LLMUnavailableError, ask_llm, provider_order


def make_settings(primary="groq") -> Settings:
    return Settings(
        GROQ_API_KEY="test",
        GOOGLE_API_KEY="test",
        PRIMARY_LLM_PROVIDER=primary,
        UPSTASH_REDIS_REST_URL="https://example.com",
        UPSTASH_REDIS_REST_TOKEN="test",
        PORTFOLIO_PROFILE_URL="https://example.com/profile.json",
    )


class LLMProviderTest(unittest.IsolatedAsyncioTestCase):
    def test_provider_order_follows_primary_config(self):
        self.assertEqual(provider_order(make_settings("groq")), ("groq", "google"))
        self.assertEqual(provider_order(make_settings("google")), ("google", "groq"))

    async def test_falls_back_to_secondary_provider(self):
        with patch("app.llm._ask_provider", new=AsyncMock(side_effect=[RuntimeError("down"), {"answer": "ok"}])):
            result, provider = await ask_llm(make_settings("groq"), {}, "hello")

        self.assertEqual(result, {"answer": "ok"})
        self.assertEqual(provider, "google")

    async def test_raises_when_all_providers_fail(self):
        with patch("app.llm._ask_provider", new=AsyncMock(side_effect=RuntimeError("down"))):
            with self.assertRaises(LLMUnavailableError):
                await ask_llm(make_settings("google"), {}, "hello")


if __name__ == "__main__":
    unittest.main()
