from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.cache import get_cached_answer, set_cached_answer
from app.config import get_settings
from app.llm import LLMUnavailableError, ask_llm, provider_order
from app.profile import fetch_profile
from app.rate_limit import Outcome, reserve_request, settle_request
from app.redis_client import RedisClient
from app.schemas import ChatRequest, ChatResponse

settings = get_settings()
redis = RedisClient(settings)

app = FastAPI(title="ZSK AI Resume API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-LLM-Provider"],
)


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/health")
async def health() -> dict[str, str]:
    primary, fallback = provider_order(settings)
    try:
        await redis.command("PING")
        cache = "connected"
    except Exception:
        cache = "error"

    return {
        "status": "ok",
        "primary_provider": primary,
        "fallback_provider": fallback,
        "cache": cache,
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request, response: Response) -> ChatResponse:
    ip = client_ip(request)
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
    cached = await get_cached_answer(redis, message, settings.cache_version)
    if cached:
        return cached.model_copy(update={"cached": True})

    profile = await fetch_profile(settings)
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
    await set_cached_answer(redis, message, chat_response, settings.cache_ttl_seconds, settings.cache_version)
    return chat_response
