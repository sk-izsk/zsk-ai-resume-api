import httpx

from app.config import Settings


class RedisClient:
    """Upstash over REST, on one shared connection pool instead of a new connection per command."""

    def __init__(self, settings: Settings):
        self.base_url = settings.upstash_redis_rest_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=5,
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
        )

    async def command(self, *parts: str | int) -> object:
        response = await self._http.post(self.base_url, json=[str(part) for part in parts])
        response.raise_for_status()
        return response.json().get("result")

    async def pipeline(self, *commands: list[str | int]) -> list[object]:
        """Several commands in one round trip, run in order. Raises if any of them failed."""
        response = await self._http.post(
            f"{self.base_url}/pipeline",
            json=[[str(part) for part in command] for command in commands],
        )
        response.raise_for_status()
        replies = response.json()
        errors = [reply["error"] for reply in replies if "error" in reply]
        if errors:
            raise RuntimeError(f"Redis pipeline failed: {errors}")
        return [reply.get("result") for reply in replies]

    async def aclose(self) -> None:
        await self._http.aclose()
