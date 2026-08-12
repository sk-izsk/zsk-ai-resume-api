import httpx

from app.config import Settings


class RedisClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.upstash_redis_rest_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {settings.upstash_redis_rest_token}"}

    async def command(self, *parts: str | int) -> object:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                self.base_url,
                headers=self.headers,
                json=[str(part) for part in parts],
            )
            response.raise_for_status()
            payload = response.json()
            return payload.get("result")
