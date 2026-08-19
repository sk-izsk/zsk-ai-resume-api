from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=10_000)


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []
    blocked: bool = False
    remaining: int
    reset_in_seconds: int
    cached: bool = False
    provider: str | None = None


class RateLimitState(BaseModel):
    allowed: bool
    remaining: int
    reset_in_seconds: int
