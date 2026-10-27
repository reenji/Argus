"""Translate Gemini client failures into HTTP errors the web client can show."""

from __future__ import annotations

from fastapi import HTTPException, status

from .errors import api_error as _error


_KEY_REJECTED_MARKERS = ("api key not valid", "api_key_invalid", "invalid api key")


def gemini_http_error(exc: BaseException) -> HTTPException:
    import httpx
    from google.genai import errors

    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return _error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "gemini_timeout",
            "Gemini took too long to answer. Please try again.",
        )
    if isinstance(exc, errors.APIError):
        code = int(exc.code or 0)
        text = f"{exc.status or ''} {exc.message or ''}".lower()
        if code in {401, 403} or any(marker in text for marker in _KEY_REJECTED_MARKERS):
            return _error(
                status.HTTP_409_CONFLICT,
                "gemini_key_rejected",
                "Gemini rejected your API key. Update it in settings and try again.",
            )
        if code == 429:
            return _error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "gemini_quota_exceeded",
                "Your Gemini quota is used up for now. Please try again later.",
                headers={"Retry-After": "60"},
            )
        if code >= 500:
            return _error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "gemini_unavailable",
                "Gemini is unavailable right now. Please try again shortly.",
            )
    if isinstance(exc, httpx.TransportError):
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "gemini_unavailable",
            "Gemini could not be reached. Please try again shortly.",
        )
    return _error(
        status.HTTP_502_BAD_GATEWAY,
        "gemini_failed",
        "Gemini could not answer this message. Please try again.",
    )
