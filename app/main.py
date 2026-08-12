from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.cache import get_cached_answer, set_cached_answer
from app.config import get_settings
from app.groq_client import RateLimitError, ask_groq
from app.profile import fetch_profile
from app.rate_limit import check_rate_limit
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
)


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    limit = await check_rate_limit(redis, settings, client_ip(request))
    if not limit.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Rate limit exceeded",
                "remaining": limit.remaining,
                "reset_in_seconds": limit.reset_in_seconds,
            },
        )

    cached = await get_cached_answer(redis, payload.message, settings.cache_version)
    if cached:
        return cached.model_copy(
            update={
                "remaining": limit.remaining,
                "reset_in_seconds": limit.reset_in_seconds,
                "cached": True,
            }
        )

    profile = await fetch_profile(settings)
    try:
        ai_result = await ask_groq(settings, profile, payload.message)
    except RateLimitError as error:
        raise HTTPException(
            status_code=429,
            detail={
                "message": "Groq model token limit reached. Try again later.",
                "provider_error": str(error),
            },
        ) from error

    response = ChatResponse(
        answer=str(ai_result.get("answer", "")).strip(),
        sources=list(ai_result.get("sources", [])),
        blocked=bool(ai_result.get("blocked", False)),
        remaining=limit.remaining,
        reset_in_seconds=limit.reset_in_seconds,
    )
    await set_cached_answer(redis, payload.message, response, settings.cache_ttl_seconds, settings.cache_version)
    return response
