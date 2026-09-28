"""Framework-independent HTTP errors shared by RAG operations and Django views."""

from __future__ import annotations

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


ERRORS: dict[int, tuple[str, str, bool]] = {
    400: ("INVALID_REQUEST", "The request is invalid.", False),
    404: ("NOT_FOUND", "The requested resource was not found.", False),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed.", False),
    409: ("CONFLICT", "The request conflicts with the current state.", True),
    413: ("PAYLOAD_TOO_LARGE", "The request payload is too large.", False),
    415: ("UNSUPPORTED_MEDIA_TYPE", "The media type is not supported.", False),
    422: ("VALIDATION_ERROR", "Request validation failed.", False),
    429: ("RATE_LIMITED", "The upstream model rate limit was exceeded.", True),
    500: ("INTERNAL_ERROR", "An internal error occurred.", True),
    502: ("UPSTREAM_RESPONSE_ERROR", "The upstream model response failed.", True),
    503: ("SERVICE_UNAVAILABLE", "The service is unavailable.", True),
    504: ("UPSTREAM_TIMEOUT", "The upstream model request timed out.", True),
}


def error_payload(status_code: int, message: str | None = None) -> dict:
    code, default_message, retryable = ERRORS.get(
        status_code, ("HTTP_ERROR", "The request failed.", status_code >= 500)
    )
    resolved = message or default_message
    if status_code == 409 and "RAG index" in resolved:
        code = "RAG_INDEX_NOT_READY"
    return {"error": {"code": code, "message": resolved, "retryable": retryable}}


def upstream_http_exception(exc: Exception, *, fallback_message: str) -> ApiError:
    """Translate model provider failures to the public HTTP contract."""
    if isinstance(exc, RateLimitError):
        return ApiError(429, "The upstream model rate limit was exceeded.")
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return ApiError(504, "The upstream model request timed out.")
    if isinstance(exc, (APIConnectionError, ConnectionError)):
        return ApiError(503, "The upstream model service is unavailable.")
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return ApiError(429, "The upstream model rate limit was exceeded.")
        if exc.status_code >= 500:
            return ApiError(503, "The upstream model service is unavailable.")
    return ApiError(502, fallback_message)
