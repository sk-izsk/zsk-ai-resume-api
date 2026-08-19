import unittest

from pydantic import ValidationError

from app.schemas import ChatRequest


class ChatRequestTest(unittest.TestCase):
    def test_accepts_long_job_description_sized_message(self):
        request = ChatRequest(message="x" * 10_000)

        self.assertEqual(len(request.message), 10_000)

    def test_rejects_messages_over_limit(self):
        with self.assertRaises(ValidationError):
            ChatRequest(message="x" * 10_001)


if __name__ == "__main__":
    unittest.main()
