import json
import logging
from typing import Literal

from app.config import Settings
from app.groq_client import SYSTEM_PROMPT, ask_groq, compact_profile

ProviderName = Literal["groq", "google"]

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    pass


def provider_order(settings: Settings) -> tuple[ProviderName, ProviderName]:
    primary = settings.primary_llm_provider
    fallback: ProviderName = "google" if primary == "groq" else "groq"
    return primary, fallback


def build_user_prompt(profile: dict, message: str) -> str:
    return (
        "RESUME_PROFILE_JSON:\n"
        f"{json.dumps(compact_profile(profile, message), ensure_ascii=False)}\n\n"
        f"USER_QUESTION:\n{message}"
    )


async def ask_google(settings: Settings, profile: dict, message: str) -> dict:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.google_api_key,
        http_options=types.HttpOptions(timeout=30_000),
    )
    try:
        chat = client.aio.chats.create(
            model=settings.google_model,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        response = await chat.send_message(build_user_prompt(profile, message))
        return json.loads(response.text or "{}")
    finally:
        await client.aio.aclose()


async def _ask_provider(provider: ProviderName, settings: Settings, profile: dict, message: str) -> dict:
    if provider == "groq":
        return await ask_groq(settings, profile, message)
    return await ask_google(settings, profile, message)


async def ask_llm(settings: Settings, profile: dict, message: str) -> tuple[dict, ProviderName]:
    for provider in provider_order(settings):
        try:
            return await _ask_provider(provider, settings, profile, message), provider
        except Exception as error:
            logger.warning("LLM provider %s failed: %s", provider, error)

    raise LLMUnavailableError("all LLM providers failed")


__all__ = ["LLMUnavailableError", "ProviderName", "ask_google", "ask_llm", "provider_order"]
