import json
import logging
from functools import lru_cache
from typing import Literal

from google import genai
from google.genai import types

from app.config import Settings
from app.groq_client import MAX_OUTPUT_TOKENS, PROVIDER_TIMEOUT_SECONDS, ask_groq
from app.prompt import SYSTEM_PROMPT, AiReply, build_user_prompt

ProviderName = Literal["groq", "google"]

logger = logging.getLogger(__name__)


class LLMUnavailableError(Exception):
    pass


def provider_order(settings: Settings) -> tuple[ProviderName, ProviderName]:
    primary = settings.primary_llm_provider
    fallback: ProviderName = "google" if primary == "groq" else "groq"
    return primary, fallback


@lru_cache(maxsize=1)
def _google_client(api_key: str) -> genai.Client:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=PROVIDER_TIMEOUT_SECONDS * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


async def ask_google(settings: Settings, profile: dict, message: str) -> dict:
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is not configured")

    response = await _google_client(settings.google_api_key).aio.models.generate_content(
        model=settings.google_model,
        contents=build_user_prompt(profile, message),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=AiReply,
            # Answering from a resume needs little reasoning; thinking tokens are billed but never shown.
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.2,
        ),
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
