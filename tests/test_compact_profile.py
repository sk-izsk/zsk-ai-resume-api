import unittest

from app.prompt import REFUSAL_PREFIX, SYSTEM_PROMPT, build_user_prompt, compact_profile


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

    def test_french_questions_match_english_tags(self):
        projects = [{"title": f"Plain {i}", "tags": ["CSS"]} for i in range(6)]
        projects.append({"title": "Smart AI", "tags": ["AI"]})

        titles = [p["title"] for p in compact_profile({"projects": projects}, "Quels projets IA ?")["portfolio_projects"]]

        self.assertEqual(titles[0], "Smart AI")

    def test_prompt_carries_the_refusal_sentence_and_the_question(self):
        self.assertIn(REFUSAL_PREFIX, SYSTEM_PROMPT)
        self.assertTrue(build_user_prompt({}, "react?").endswith("USER_QUESTION:\nreact?"))

if __name__ == "__main__":
    unittest.main()
