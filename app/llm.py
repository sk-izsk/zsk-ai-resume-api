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

    import google.generativeai as genai

    genai.configure(api_key=settings.google_api_key)
    model = genai.GenerativeModel(settings.google_model, system_instruction=SYSTEM_PROMPT)
    response = await model.generate_content_async(
        build_user_prompt(profile, message),
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.2,
        },
        request_options={"timeout": 30},
    )
    return json.loads(response.text or "{}")


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
