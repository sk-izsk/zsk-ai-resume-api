import json
from functools import lru_cache

from groq import AsyncGroq

from app.config import Settings
from app.prompt import SYSTEM_PROMPT, build_user_prompt

# Two providers in a row must still answer inside the site's 30 s request timeout.
PROVIDER_TIMEOUT_SECONDS = 12
# Room for low-effort reasoning plus a concise answer; reasoning tokens count toward this on gpt-oss.
MAX_OUTPUT_TOKENS = 1024

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "blocked": {"type": "boolean"},
    },
    "required": ["answer", "sources", "blocked"],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def _client(api_key: str) -> AsyncGroq:
    # No SDK retries: a rate-limited Groq waits up to a minute, so hand over to the other provider instead.
    return AsyncGroq(api_key=api_key, max_retries=0, timeout=PROVIDER_TIMEOUT_SECONDS)


async def ask_groq(settings: Settings, profile: dict, message: str) -> dict:
    response = await _client(settings.groq_api_key).chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(profile, message)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "reply", "schema": REPLY_SCHEMA, "strict": True},
        },
        reasoning_effort="low",
        max_completion_tokens=MAX_OUTPUT_TOKENS,
        temperature=0.2,
    )
    return json.loads(response.choices[0].message.content or "{}")


__all__ = ["MAX_OUTPUT_TOKENS", "PROVIDER_TIMEOUT_SECONDS", "ask_groq"]
