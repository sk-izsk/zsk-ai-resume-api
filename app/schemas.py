from pydantic import BaseModel, Field

from app.prompt import REFUSAL_PREFIX


class ChatRequest(BaseModel):
    # Room for a pasted job description ("is he a fit for this role?"), about 2.5k tokens at most.
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
