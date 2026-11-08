import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.cache import get_cached_answer, set_cached_answer
from app.client_ip import client_ip
from app.config import get_settings
from app.llm import LLMUnavailableError, ask_llm, provider_order
from app.profile import get_profile
from app.prompt import PROMPT_FINGERPRINT, SUGGESTED_QUESTIONS
from app.rate_limit import Outcome, peek_usage, reserve_request, settle_request
from app.redis_client import RedisClient
from app.schemas import ChatRequest, ChatResponse, RateLimitState

logger = logging.getLogger(__name__)
settings = get_settings()
redis = RedisClient(settings)


# Spaces the warm-up out so it doesn't spend Groq's per-minute token budget in one burst.
WARM_PAUSE_SECONDS = 5


async def warm_cache() -> None:
    """Answers the site's suggested questions once, so most visitors get an instant, free reply.

    Already-cached questions cost nothing, so this only calls the AI after the profile or prompt changes.
    It stops at the first failure: if the providers are out of quota, more attempts only waste requests.
    """
    for question in SUGGESTED_QUESTIONS:
        try:
            reply = await answer_question(question)
        except Exception as error:
            logger.warning("Stopped pre-answering at %r: %s", question, error)
            return
        if not reply.cached:
            await asyncio.sleep(WARM_PAUSE_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    warming = asyncio.create_task(warm_cache())
    yield
    warming.cancel()
    await redis.aclose()


app = FastAPI(title="ZSK AI Resume API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-LLM-Provider"],
)


@app.get("/health")
async def health(deep: bool = False) -> dict[str, str]:
    """Cheap by default, since the site and Render poll it; ?deep=true also checks Redis."""
    primary, fallback = provider_order(settings)
    status = {"status": "ok", "primary_provider": primary, "fallback_provider": fallback}
    if deep:
        try:
            await redis.command("PING")
            status["cache"] = "connected"
        except Exception:
            status["cache"] = "error"
    return status


@app.get("/usage", response_model=RateLimitState)
async def usage(request: Request) -> RateLimitState:
    """The visitor's remaining requests, read without using one, so the site remembers across reloads."""
    return await peek_usage(redis, settings, client_ip(request, settings.netlify_proxy_secret))


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, response: Response) -> ChatResponse:
    ip = client_ip(request, settings.netlify_proxy_secret)
    limit = await reserve_request(redis, settings, ip)
    if not limit.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Rate limit exceeded",
                "remaining": limit.remaining,
                "reset_in_seconds": limit.reset_in_seconds,
            },
        )

    # Only real answers use up a request; refusals use the refusal cap and failures use neither.
    outcome: Outcome = "failed"
    try:
        chat_response = await answer_question(payload.message)
        outcome = "refusal" if chat_response.is_refusal else "answer"
    finally:
        limit = await settle_request(redis, settings, ip, outcome)

    response.headers["X-LLM-Provider"] = chat_response.provider or "cache"
    return chat_response.model_copy(
        update={
            "blocked": outcome == "refusal",
            "remaining": limit.remaining,
            "reset_in_seconds": limit.reset_in_seconds,
        }
    )


async def answer_question(message: str) -> ChatResponse:
    profile, fingerprint = await get_profile(settings)
    # Keyed to the profile and the prompt, so editing either refreshes answers without a manual version bump.
    cache_version = f"{settings.cache_version}:{fingerprint}:{PROMPT_FINGERPRINT}"

    cached = await get_cached_answer(redis, message, cache_version)
    if cached:
        return cached.model_copy(update={"cached": True})

    try:
        ai_result, provider = await ask_llm(settings, profile, message)
    except LLMUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "AI service temporarily unavailable. Please try again shortly.",
            },
        ) from error

    chat_response = ChatResponse(
        answer=str(ai_result.get("answer", "")).strip(),
        sources=list(ai_result.get("sources", [])),
        blocked=bool(ai_result.get("blocked", False)),
        provider=provider,
        remaining=0,
        reset_in_seconds=0,
    )
    chat_response.blocked = chat_response.is_refusal
    await set_cached_answer(redis, message, chat_response, settings.cache_ttl_seconds, cache_version)
    return chat_response
