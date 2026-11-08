import json
import re

from groq import AsyncGroq, RateLimitError

from app.config import Settings

# Two providers in a row must still answer inside the site's 30 s request timeout.
PROVIDER_TIMEOUT_SECONDS = 12


SYSTEM_PROMPT = """
# ROLE : 
You are Zeeshan's portfolio AI assistant.

# Task

Answer only questions about Zeeshan Shaikh Murshed, his resume, skills, projects,
education, experience, blog, contact links, and professional background.

#  CONSTRAINT

Use only the provided RESUME_PROFILE_JSON as source material.
Do not invent facts.
If the answer is not available in the profile, say that the portfolio does not include that detail.
If the user asks about unrelated topics, politely refuse and redirect them to ask about Zeeshan's work.

Keep answers concise, professional, and specific. Make sure to save tokens and don't waste them.
When useful, mention the exact project, skill, or experience item that supports the answer.

Evidence order matters:
1. Professional experience is always primary evidence.
2. For any question about a skill, role, technology, or "strongest projects", check professional_experience first.
3. If professional_experience contains relevant evidence, mention it before any portfolio_projects.
4. Then use portfolio_projects as supporting proof.
5. Then use skill ratings only as secondary support.
6. Never imply professional experience is missing because portfolio_projects are not labeled professional.
7. Treat professional_experience as professional work history. Treat portfolio_projects as personal/portfolio evidence unless a company/employer is explicitly stated.

#  EXAMPLES
For skill questions, answer with this structure:
- Start with a direct yes/no/qualified answer.
- Mention the most relevant professional role/company first.
- Include 1-2 concrete professional achievements or responsibilities from professional_experience.highlights.
- Then mention 1-3 portfolio projects as extra proof.
- Avoid vague answers like "he has experience at Company X" without saying what he achieved there.
- If the user asks for "best/strongest React projects", still start with professional React work first, then list portfolio projects.

# FALLBACK

If the issue is unrelated to any of the categories mentioned in constraints, then the answer should be "This is outside my expertise. I can only answer questions about Zeeshan's resume, skills, projects, education, experience, blog, contact links, and professional background."


# OUTPUT FORMAT
Return JSON only:
{
  "answer": "string",
  "sources": ["short source labels from the profile"],
  "blocked": boolean
}
""".strip()


def _matches_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def retry_after_seconds(message: str) -> int | None:
    match = re.search(r"try again in (?=\d)(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", message)
    if not match:
        return None

    hours, minutes, seconds = match.groups(default="0")
    return int(hours) * 3600 + int(minutes) * 60 + int(float(seconds))


MAX_PROJECTS = 4
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "he", "his", "in", "is", "it", "me", "my", "of",
    "on", "or", "the", "to", "what", "which", "does", "has", "have", "with", "about", "your", "this", "that",
    "best", "most", "zeeshan", "zeeshan's", "show", "tell", "built", "project", "projects", "work", "good",
}


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(word) > 1 and word not in _STOPWORDS}


def _relevant_projects(projects: list[dict], message: str) -> list[dict]:
    # ponytail: keyword overlap, not embeddings; fine for 14 projects, swap for embeddings if the list gets big.
    asked = _words(message)

    def score(project: dict) -> int:
        text = " ".join(
            [str(project.get(key, "")) for key in ("title", "category", "excerpt")] + project.get("tags", [])
        )
        return len(asked & _words(text))

    # sorted() is stable, so ties keep the profile's own order (newest/featured first).
    return sorted(projects, key=score, reverse=True)[:MAX_PROJECTS]


def compact_profile(profile: dict, message: str) -> dict:
    """Only what this question needs, so each request stays well under the providers' token limits."""
    text = message.lower()
    wants_blog = _matches_any(text, ["blog", "article", "writing", "hashnode"])
    wants_education = _matches_any(text, ["education", "degree", "master", "bootcamp", "school"])
    wants_contact = _matches_any(text, ["contact", "email", "linkedin", "github", "reach"])
    wants_stack = _matches_any(text, ["skill", "stack", "tech", "know", "tool", "framework", "librar", "language"])
    skills = profile.get("skills", {})

    compact = {
        "identity": profile.get("identity", {}),
        "summary": profile.get("summary", {}).get("short", ""),
        "skill_ratings": [f"{item.get('name')}: {item.get('level')}" for item in skills.get("technical", [])],
        "professional_experience": [
            {
                "company": item.get("company"),
                "position": item.get("position"),
                "duration": item.get("duration"),
                "description": item.get("description"),
                "highlights": item.get("highlights", [])[:3],
            }
            for item in profile.get("experience", [])
        ],
        "portfolio_projects": [
            {
                "title": item.get("title"),
                "category": item.get("category"),
                "tags": item.get("tags", [])[:8],
                "excerpt": item.get("excerpt"),
                "highlights": item.get("highlights", [])[:1],
            }
            for item in _relevant_projects(profile.get("projects", []), message)
        ],
    }

    if wants_stack:
        compact["skill_categories"] = skills.get("categories", {})

    if wants_blog:
        compact["blog"] = [
            {
                "title": item.get("title"),
                "tags": item.get("tags", [])[:8],
                "excerpt": item.get("excerpt"),
            }
            for item in profile.get("blog", [])
        ]

    if wants_education:
        compact["education"] = profile.get("education", [])

    if wants_contact:
        compact["contact"] = profile.get("contact", {})

    return compact


async def ask_groq(settings: Settings, profile: dict, message: str) -> dict:
    # No SDK retries: a rate-limited Groq waits up to a minute, so hand over to the other provider instead.
    client = AsyncGroq(api_key=settings.groq_api_key, max_retries=0, timeout=PROVIDER_TIMEOUT_SECONDS)
    response = await client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "RESUME_PROFILE_JSON:\n"
                    f"{json.dumps(compact_profile(profile, message), ensure_ascii=False)}\n\n"
                    f"USER_QUESTION:\n{message}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


__all__ = ["RateLimitError", "ask_groq", "compact_profile", "retry_after_seconds"]
