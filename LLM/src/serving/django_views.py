"""Django HTTP boundary for the framework-neutral RAG operations."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from html import escape
from typing import Any

from asgiref.sync import sync_to_async
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import BaseModel, ValidationError

from src.core.config import get_settings
from src.serving.api_schema import ROUTES, openapi_document
from src.serving.errors import ApiError, error_payload
from src.serving import rag_routes
from src.serving.schemas import (
    AnnouncementSummaryRequest,
    ComponentConfiguration,
    DeductibilityRequest,
    HealthResponse,
    IndexRequest,
    LegalBasisRequest,
    PolicyRecommendationRequest,
    RagAnswerRequest,
    RagChatRequest,
    RagReindexRequest,
)


logger = logging.getLogger(__name__)
APP_VERSION = "0.1.0"
_runtime = rag_routes.RagRuntime()


def get_runtime() -> rag_routes.RagRuntime:
    return _runtime


def set_runtime(runtime: rag_routes.RagRuntime) -> None:
    """Replace the process runtime in tests without touching the production graph."""
    global _runtime
    _runtime = runtime


def _error(status_code: int, message: str | None = None) -> JsonResponse:
    return JsonResponse(error_payload(status_code, message), status=status_code)


def _method_not_allowed(method: str) -> JsonResponse:
    response = _error(405)
    response["Allow"] = method
    return response


def page_not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return _error(404)


def server_error(request: HttpRequest) -> JsonResponse:
    logger.error(
        "Unhandled LLM API error: method=%s path=%s", request.method, request.path
    )
    return _error(500)


def openapi(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return _method_not_allowed("GET")
    return JsonResponse(openapi_document())


def docs(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return _method_not_allowed("GET")
    rows = "".join(
        "<tr><td>{}</td><td><code>{}</code></td><td>{}</td><td>{}</td></tr>".format(
            method.upper(), escape(path),
            escape(request_model.__name__ if request_model else "—"),
            escape(response_model.__name__),
        )
        for path, method, request_model, response_model in ROUTES
    )
    return HttpResponse(
        '<!doctype html><html><head><meta charset="utf-8"><title>LLM API</title>'
        '<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">'
        '</head><body><div id="swagger-ui"><h1>LLM API</h1>'
        '<p>OpenAPI schema: <a href="/openapi.json">/openapi.json</a></p>'
        '<table><thead><tr><th>Method</th><th>Path</th><th>Request</th>'
        '<th>Response</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
        '<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>'
        '<script>SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui"});</script>'
        '</body></html>',
        content_type="text/html",
    )


def _validation_error(exc: ValidationError) -> JsonResponse:
    messages = []
    for issue in exc.errors()[:5]:
        location = ".".join(str(part) for part in issue.get("loc", ()))
        reason = str(issue.get("msg") or "invalid value")
        messages.append(f"body.{location}: {reason}" if location else f"body: {reason}")
    return _error(422, "; ".join(messages) or "Request validation failed.")


def _json_result(result: BaseModel | dict[str, Any]) -> JsonResponse:
    payload = result.model_dump(mode="json") if isinstance(result, BaseModel) else result
    return JsonResponse(payload)


async def _dispatch(
    request: HttpRequest,
    *,
    method: str,
    handler: Callable[..., Awaitable[BaseModel]],
    schema: type[BaseModel] | None = None,
    optional_body: bool = False,
) -> HttpResponse:
    if request.method != method:
        return _method_not_allowed(method)
    try:
        if method == "POST" and schema is not None:
            payload = request.body
            if payload and request.content_type != "application/json":
                return _error(415, "Content-Type must be application/json")
            body = schema.model_validate_json(payload) if payload else (
                None if optional_body else schema.model_validate_json(payload)
            )
            result = await handler(body, _runtime, get_settings())
        else:
            result = await handler(_runtime, get_settings())
        return _json_result(result)
    except ValidationError as exc:
        return _validation_error(exc)
    except RequestDataTooBig:
        return _error(413)
    except ApiError as exc:
        return _error(exc.status_code, exc.detail)
    except Exception:
        logger.exception("LLM API request failed: method=%s path=%s", request.method, request.path)
        return _error(500)


@csrf_exempt
async def health(request: HttpRequest) -> HttpResponse:
    if request.method != "GET":
        return _method_not_allowed("GET")
    settings = get_settings()
    return _json_result(HealthResponse(
        service=settings.app_name,
        version=APP_VERSION,
        components=ComponentConfiguration(
            llm="configured" if settings.llm_configured else "not_configured",
            embedding="configured" if settings.embedding_configured else "not_configured",
            data_source=settings.vector_store_backend,
        ),
    ))


@csrf_exempt
async def internal_ready(request: HttpRequest) -> HttpResponse:
    return await _dispatch(request, method="GET", handler=rag_routes.ready)


@csrf_exempt
async def public_ready(request: HttpRequest) -> HttpResponse:
    return await _dispatch(request, method="GET", handler=rag_routes.adapter_ready)


@csrf_exempt
async def internal_index(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.create_index,
        schema=IndexRequest, optional_body=True,
    )


@csrf_exempt
async def public_reindex(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.adapter_reindex,
        schema=RagReindexRequest, optional_body=True,
    )


@csrf_exempt
async def internal_answer(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.answer, schema=RagAnswerRequest,
    )


@csrf_exempt
async def internal_recommendations(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.recommend_policies,
        schema=PolicyRecommendationRequest,
    )


@csrf_exempt
async def public_chat(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.adapter_chat, schema=RagChatRequest,
    )


@csrf_exempt
async def public_legal_basis(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.adapter_legal_basis,
        schema=LegalBasisRequest,
    )


@csrf_exempt
async def public_deductibility(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.adapter_deductibility,
        schema=DeductibilityRequest,
    )


@csrf_exempt
async def public_summarize_announcement(request: HttpRequest) -> HttpResponse:
    return await _dispatch(
        request, method="POST", handler=rag_routes.adapter_summarize_announcement,
        schema=AnnouncementSummaryRequest,
    )


class _AsyncUploadedFile:
    def __init__(self, file: Any) -> None:
        self.file = file
        self.content_type = file.content_type

    async def read(self, size: int = -1) -> bytes:
        return await sync_to_async(self.file.read, thread_sensitive=True)(size)


@csrf_exempt
async def receipt_ocr(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        return _method_not_allowed("POST")
    if request.content_type != "multipart/form-data":
        return _error(415, "Content-Type must be multipart/form-data")
    try:
        upload = await sync_to_async(lambda: request.FILES.get("image"), thread_sensitive=True)()
        if upload is None:
            return _error(422, "body.image: Field required")
        result = await rag_routes.adapter_receipt_ocr(_AsyncUploadedFile(upload), _runtime)
        return _json_result(result)
    except RequestDataTooBig:
        return _error(413)
    except ApiError as exc:
        return _error(exc.status_code, exc.detail)
    except Exception:
        logger.exception("LLM OCR request failed")
        return _error(500)
