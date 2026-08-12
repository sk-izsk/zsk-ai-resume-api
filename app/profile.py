import json
from pathlib import Path

import httpx

from app.config import Settings


async def fetch_profile(settings: Settings) -> dict:
    if settings.portfolio_profile_path:
        return json.loads(Path(settings.portfolio_profile_path).read_text(encoding="utf-8"))

    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(settings.portfolio_profile_url)
        response.raise_for_status()
        return response.json()
