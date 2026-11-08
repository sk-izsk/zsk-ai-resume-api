import unittest

from app.groq_client import compact_profile, retry_after_seconds


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

        self.assertIn("professional_experience", compact)
        self.assertIn("portfolio_projects", compact)
        self.assertNotIn("blog", compact)
        self.assertNotIn("education", compact)
        self.assertNotIn("contact", compact)
        self.assertNotIn("skill_categories", compact)
        self.assertEqual(compact["skill_ratings"], ["React: None"])
        self.assertEqual(len(compact["professional_experience"][0]["highlights"]), 3)
        self.assertEqual(len(compact["portfolio_projects"][0]["tags"]), 8)

    def test_sends_only_the_projects_that_match_the_question(self):
        projects = [{"title": f"Plain {i}", "tags": ["CSS"]} for i in range(6)]
        projects.append({"title": "Smart AI", "tags": ["OpenAI"], "category": "AI Engineering"})
        profile = {"projects": projects}

        titles = [p["title"] for p in compact_profile(profile, "What AI projects has he built?")["portfolio_projects"]]

        self.assertEqual(len(titles), 4)
        self.assertEqual(titles[0], "Smart AI")

    def test_parses_groq_retry_after_seconds(self):
        self.assertEqual(retry_after_seconds("Please try again in 2h3m4.5s."), 7384)
        self.assertEqual(retry_after_seconds("Please try again in 3m16.992s."), 196)
        self.assertIsNone(retry_after_seconds("No retry hint"))


if __name__ == "__main__":
    unittest.main()
