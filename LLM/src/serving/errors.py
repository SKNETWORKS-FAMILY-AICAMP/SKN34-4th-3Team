"""LLM HTTP API의 오류 응답을 단일 계약으로 변환한다."""

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from starlette.exceptions import HTTPException as StarletteHTTPException


logger = logging.getLogger(__name__)

_DEFAULT_ERRORS: dict[int, tuple[str, str, bool]] = {
    400: ("INVALID_REQUEST", "The request is invalid.", False),
    404: ("NOT_FOUND", "The requested resource was not found.", False),
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


def upstream_http_exception(
    exc: Exception,
    *,
    fallback_message: str,
) -> HTTPException:
    """외부 모델 예외를 재시도 가능성이 드러나는 HTTP 상태로 변환한다."""
    if isinstance(exc, RateLimitError):
        return HTTPException(
            status_code=429,
            detail="The upstream model rate limit was exceeded.",
        )
    if isinstance(exc, (APITimeoutError, TimeoutError)):
        return HTTPException(
            status_code=504,
            detail="The upstream model request timed out.",
        )
    if isinstance(exc, (APIConnectionError, ConnectionError)):
        return HTTPException(
            status_code=503,
            detail="The upstream model service is unavailable.",
        )
    if isinstance(exc, APIStatusError):
        if exc.status_code == 429:
            return HTTPException(
                status_code=429,
                detail="The upstream model rate limit was exceeded.",
            )
        if exc.status_code >= 500:
            return HTTPException(
                status_code=503,
                detail="The upstream model service is unavailable.",
            )
    return HTTPException(status_code=502, detail=fallback_message)


async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    """FastAPI·Starlette HTTPException을 공통 ErrorResponse로 변환한다."""
    code, default_message, retryable = _error_definition(exc.status_code)
    message = exc.detail if isinstance(exc.detail, str) else default_message
    if exc.status_code == 409 and "RAG index" in message:
        code = "RAG_INDEX_NOT_READY"
    return _response(exc.status_code, code, message, retryable)


async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Pydantic 요청 검증 오류에서 입력값을 제외한 위치와 사유만 반환한다."""
    messages = []
    for error in exc.errors()[:5]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        reason = str(error.get("msg") or "invalid value")
        messages.append(f"{location}: {reason}" if location else reason)
    message = "; ".join(messages) or "Request validation failed."
    return _response(422, "VALIDATION_ERROR", message, False)


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """처리되지 않은 예외를 기록하고 내부 상세를 숨긴다."""
    logger.exception(
        "Unhandled LLM API error: method=%s path=%s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return _response(
        500,
        "INTERNAL_ERROR",
        "An internal error occurred.",
        True,
    )


def _error_definition(status_code: int) -> tuple[str, str, bool]:
    """HTTP 상태에 맞는 안정적인 오류 코드·기본 메시지를 반환한다."""
    return _DEFAULT_ERRORS.get(
        status_code,
        ("HTTP_ERROR", "The request failed.", 500 <= status_code),
    )


def _response(
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
) -> JSONResponse:
    """공통 오류 JSONResponse를 생성한다."""
    content: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    }
    return JSONResponse(status_code=status_code, content=content)
