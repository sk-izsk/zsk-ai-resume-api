import unittest

from app.groq_client import compact_profile


class CompactProfileTest(unittest.TestCase):
    def test_keeps_core_profile_and_skips_optional_sections_by_default(self):
        profile = {
            "identity": {"name": "Zeeshan"},
            "summary": {"short": "Engineer"},
            "skills": {"technical": [{"name": "React"}], "categories": {"frontend": ["React"]}},
            "experience": [{"company": "A", "highlights": ["1", "2", "3", "4", "5"]}],
            "projects": [{"title": "P", "tags": list("abcdefghijkl"), "highlights": ["1", "2", "3"]}],
            "blog": [{"title": "B"}],
            "education": [{"degree": "D"}],
            "contact": {"email": "x@y.com"},
        }

        compact = compact_profile(profile, "is he good at react?")

        self.assertIn("experience", compact)
        self.assertIn("projects", compact)
        self.assertNotIn("blog", compact)
        self.assertNotIn("education", compact)
        self.assertNotIn("contact", compact)
        self.assertEqual(len(compact["experience"][0]["highlights"]), 4)
        self.assertEqual(len(compact["projects"][0]["tags"]), 10)


if __name__ == "__main__":
    unittest.main()
