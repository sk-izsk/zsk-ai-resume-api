import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

# (fetched_at, profile, fingerprint). ponytail: no lock, so two requests can refetch at once on expiry; harmless.
_cached: tuple[float, dict, str] | None = None


def _fingerprint(profile: dict) -> str:
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode("utf-8")).hexdigest()[:12]


async def _download(settings: Settings) -> dict:
    if settings.portfolio_profile_path:
        return json.loads(Path(settings.portfolio_profile_path).read_text(encoding="utf-8"))

    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.get(settings.portfolio_profile_url)
        response.raise_for_status()
        return response.json()


async def get_profile(settings: Settings) -> tuple[dict, str]:
    """The profile and a fingerprint of its contents, refreshed every PROFILE_TTL_SECONDS.

    If a refresh fails, the last good copy keeps answering, so the portfolio site being slow
    or down doesn't take the chat with it.
    """
    global _cached
    if _cached and time.monotonic() - _cached[0] < settings.profile_ttl_seconds:
        return _cached[1], _cached[2]

    try:
        profile = await _download(settings)
    except Exception as error:
        if not _cached:
            raise
        logger.warning("Profile refresh failed, using the last good copy: %s", error)
        return _cached[1], _cached[2]

    _cached = (time.monotonic(), profile, _fingerprint(profile))
    return profile, _cached[2]
