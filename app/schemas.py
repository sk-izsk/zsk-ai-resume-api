from pydantic import BaseModel, Field

# Kept in step with the FALLBACK answer in SYSTEM_PROMPT (app/groq_client.py).
REFUSAL_PREFIX = "This is outside my expertise"


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

    @property
    def is_refusal(self) -> bool:
        # The model doesn't always set "blocked", but its refusals always open with the fixed sentence.
        return self.blocked or not self.answer or self.answer.startswith(REFUSAL_PREFIX)


class RateLimitState(BaseModel):
    allowed: bool
    remaining: int
    reset_in_seconds: int
