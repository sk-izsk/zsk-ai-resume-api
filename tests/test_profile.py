import unittest
from unittest.mock import AsyncMock, patch

from app import profile
from app.config import Settings


def make_settings() -> Settings:
    return Settings(
        GROQ_API_KEY="test",
        UPSTASH_REDIS_REST_URL="https://example.com",
        UPSTASH_REDIS_REST_TOKEN="test",
        PORTFOLIO_PROFILE_URL="https://example.com/profile.json",
        PROFILE_TTL_SECONDS=0,
    )


class ProfileTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        profile._cached = None

    async def test_keeps_answering_from_the_last_good_copy_when_a_refresh_fails(self):
        download = AsyncMock(side_effect=[{"name": "Zeeshan"}, ConnectionError("site down")])
        with patch.object(profile, "_download", download):
            first, first_print = await profile.get_profile(make_settings())
            second, second_print = await profile.get_profile(make_settings())

        self.assertEqual(second, first)
        self.assertEqual(second_print, first_print)

    async def test_the_fingerprint_changes_with_the_contents(self):
        download = AsyncMock(side_effect=[{"name": "Zeeshan"}, {"name": "Zeeshan", "city": "Montreal"}])
        with patch.object(profile, "_download", download):
            _, before = await profile.get_profile(make_settings())
            _, after = await profile.get_profile(make_settings())

        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
