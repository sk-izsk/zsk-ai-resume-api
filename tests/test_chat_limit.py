import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://example.com")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "test")
os.environ.setdefault("PORTFOLIO_PROFILE_URL", "https://example.com/profile.json")

from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402
from app.llm import LLMUnavailableError  # noqa: E402
from test_rate_limit import FakeRedis, make_settings  # noqa: E402


async def no_profile(settings):
    return {}, "test-profile"


class ChatLimitTest(unittest.TestCase):
    """Only real answers use up one of the visitor's requests."""

    def setUp(self):
        patches = [
            patch.object(main, "redis", FakeRedis()),
            patch.object(main, "settings", make_settings(CACHE_VERSION="test")),
            patch.object(main, "get_profile", no_profile),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.client = TestClient(main.app, raise_server_exceptions=False)

    def ask(self, message, result=None, error=None):
        async def fake_llm(settings, profile, text):
            if error:
                raise error
            return result, "google"

        with patch.object(main, "ask_llm", fake_llm):
            return self.client.post("/chat", json={"message": message})

    def test_a_real_answer_uses_up_a_request(self):
        response = self.ask("react?", {"answer": "Yes, at SwiftConnect.", "blocked": False})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["remaining"], 2)

    def test_off_topic_refusals_and_failures_are_free(self):
        refused = self.ask("poem?", {"answer": "This is outside my expertise.", "blocked": True})
        failed = self.ask("react?", error=LLMUnavailableError("down"))
        answered = self.ask("skills?", {"answer": "React and TypeScript.", "blocked": False})

        self.assertEqual(refused.json()["remaining"], 3)
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(answered.json()["remaining"], 2)

    def test_a_refusal_the_model_forgot_to_flag_is_still_free(self):
        response = self.ask("pasta?", {"answer": "This is outside my expertise. I can only answer...", "blocked": False})

        self.assertTrue(response.json()["blocked"])
        self.assertEqual(response.json()["remaining"], 3)

    def test_an_unexpected_error_gives_the_slot_back(self):
        failed = self.ask("react?", error=RuntimeError("profile fetch broke"))
        answered = self.ask("skills?", {"answer": "React.", "blocked": False})

        self.assertEqual(failed.status_code, 500)
        self.assertEqual(answered.json()["remaining"], 2)

    def test_too_many_refusals_are_refused(self):
        for index in range(10):
            self.ask(f"poem {index}?", {"answer": "Outside my expertise.", "blocked": True})

        response = self.ask("poem 11?", {"answer": "Outside my expertise.", "blocked": True})

        self.assertEqual(response.status_code, 429)

    def test_usage_reports_what_is_left_without_using_it(self):
        self.ask("one?", {"answer": "ok", "blocked": False})

        first = self.client.get("/usage").json()
        second = self.client.get("/usage").json()

        self.assertEqual(first["remaining"], 2)
        self.assertEqual(second["remaining"], 2)
        self.assertTrue(first["allowed"])
        self.assertEqual(first["reset_in_seconds"], 3600)

    def test_usage_shows_zero_once_the_limit_is_reached(self):
        for question in ["one?", "two?", "three?"]:
            self.ask(question, {"answer": "ok", "blocked": False})

        usage = self.client.get("/usage").json()

        self.assertEqual(usage["remaining"], 0)
        self.assertFalse(usage["allowed"])

    def test_the_fourth_real_answer_is_refused(self):
        for question in ["one?", "two?", "three?"]:
            self.ask(question, {"answer": "ok", "blocked": False})

        response = self.ask("four?", {"answer": "ok", "blocked": False})

        self.assertEqual(response.status_code, 429)



class WarmCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_stops_at_the_first_failure_instead_of_spending_more_requests(self):
        cached = main.ChatResponse(answer="ok", remaining=0, reset_in_seconds=0, cached=True)
        answer = AsyncMock(side_effect=[cached, LLMUnavailableError("out of quota"), cached])

        with patch.object(main, "answer_question", answer):
            await main.warm_cache()

        self.assertEqual(answer.await_count, 2)


if __name__ == "__main__":
    unittest.main()
