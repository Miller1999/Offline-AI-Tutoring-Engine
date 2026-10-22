"""Shared FastAPI dependencies."""

from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings
from app.core.security import RateLimiter


@lru_cache
def get_rate_limiter() -> RateLimiter:
    """Return the process-wide rate limiter, built from the current settings."""
    settings = get_settings()
    return RateLimiter(
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )


def get_client_ip(request: Request) -> str:
    """Return the IP address of the caller.

    ``X-Forwarded-For`` takes precedence so the limiter keeps working when the
    application sits behind a reverse proxy.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    if request.client is not None:
        return request.client.host

    return "unknown"
