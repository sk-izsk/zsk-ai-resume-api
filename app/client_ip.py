"""The visitor's real IP, from headers set by a proxy we trust, never from what the client sends.

Production traffic arrives either through the site's Netlify proxy or straight at Render, and Render
sits behind Cloudflare. Cloudflare overwrites CF-Connecting-IP with the address that connected to it,
so a client can't fake it. Through Netlify that address is Netlify's, so the visitor's address comes
from X-Nf-Client-Connection-Ip instead, which is only believed when Netlify signed the request
(the `signed` option on the proxy rule, checked here with NETLIFY_PROXY_SECRET).
"""

import base64
import hashlib
import hmac
import json
import logging
import time

from starlette.requests import Request

logger = logging.getLogger(__name__)
_warned_unsigned = False


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def is_signed_by_netlify(token: str | None, secret: str | None) -> bool:
    """Checks the HS256 JWS Netlify puts in X-Nf-Sign on proxied requests."""
    if not token or not secret:
        return False
    try:
        header, payload, signature = token.split(".")
        if json.loads(_b64decode(header)).get("alg") != "HS256":
            return False
        expected = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64decode(signature), expected):
            return False
        claims = json.loads(_b64decode(payload))
        return claims.get("iss") == "netlify" and claims.get("exp", float("inf")) > time.time()
    except (ValueError, AttributeError):
        return False


def client_ip(request: Request, netlify_secret: str | None) -> str:
    global _warned_unsigned
    headers = request.headers
    netlify_ip = headers.get("x-nf-client-connection-ip")

    if netlify_ip:
        if is_signed_by_netlify(headers.get("x-nf-sign"), netlify_secret):
            return netlify_ip
        if not netlify_secret:
            # ponytail: until NETLIFY_PROXY_SECRET is set this header can be faked; set it to close that.
            if not _warned_unsigned:
                logger.warning("NETLIFY_PROXY_SECRET is not set, so the Netlify client IP header is unverified")
                _warned_unsigned = True
            return netlify_ip

    return headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
