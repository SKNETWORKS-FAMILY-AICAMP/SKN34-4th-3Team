"""Contract checks for the Django ASGI boundary without external API calls."""

import asyncio
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.serving.django_config.settings")

import django
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from src.serving import django_views
from src.serving.django_config import asgi
from src.serving.errors import ApiError
from src.serving.schemas import IndexResponse, RagChatResponse, ReceiptExtractionResponse


django.setup()


def test_health_ready_and_cors() -> None:
    client = Client()
    health = client.get("/health")
    ready = client.get("/rag/ready")
    preflight = client.options(
        "/health",
        HTTP_ORIGIN="http://localhost:5173",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert ready.status_code == 200
    assert ready.json()["index_ready"] is False
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_keeps_public_contract(monkeypatch) -> None:
    seen = []

    async def fake_chat(body, runtime, settings):
        seen.append((body, runtime, settings))
        return RagChatResponse(
            answer="근거가 없습니다.", sources=[], grounded=False,
            route="tax", status="no_result",
        )

    monkeypatch.setattr(django_views.rag_routes, "adapter_chat", fake_chat)
    response = Client().post(
        "/rag/chat",
        data='{"category":"tax","question":"세금은 어떻게 신고하나요?"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == "no_result"
    assert seen[0][0].question == "세금은 어떻게 신고하나요?"


def test_bad_chat_body_is_422_without_exposing_input() -> None:
    response = Client().post(
        "/rag/chat", data='{"category":"tax"}', content_type="application/json"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_receipt_multipart_is_forwarded(monkeypatch) -> None:
    async def fake_receipt(image, runtime):
        assert image.content_type == "image/png"
        assert await image.read(10) == b"image-data"
        return ReceiptExtractionResponse(vendor="상점", amount=1000)

    monkeypatch.setattr(django_views.rag_routes, "adapter_receipt_ocr", fake_receipt)
    response = Client().post(
        "/ocr/receipt",
        {"image": SimpleUploadedFile("receipt.png", b"image-data", content_type="image/png")},
    )
    assert response.status_code == 200
    assert response.json()["amount"] == 1000


def test_wrong_method_is_405() -> None:
    response = Client().get("/rag/chat")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert response.headers["Allow"] == "POST"


def test_unknown_path_and_api_docs() -> None:
    client = Client()
    missing = client.get("/not-a-real-endpoint")
    docs = client.get("/docs")
    schema = client.get("/openapi.json")
    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "NOT_FOUND", "message": "The requested resource was not found.", "retryable": False,
    }
    assert docs.status_code == 200
    assert b"SwaggerUIBundle" in docs.content
    assert b"<table>" in docs.content
    assert b"/rag/chat" in docs.content
    assert schema.status_code == 200
    assert schema.json()["openapi"] == "3.1.0"


def test_asgi_starts_index_warmup_once_on_http(monkeypatch) -> None:
    calls = []

    async def fake_warmup():
        calls.append("warmup")

    async def fake_django(scope, receive, send):
        calls.append(scope["type"])

    monkeypatch.setattr(asgi, "_warmup_task", None)
    monkeypatch.setattr(asgi, "_warm_up", fake_warmup)
    monkeypatch.setattr(asgi, "_django_application", fake_django)

    async def exercise():
        for scope_type in ("lifespan", "http", "http"):
            await asgi.application({"type": scope_type}, None, None)
            await asyncio.sleep(0)

    asyncio.run(exercise())
    assert calls == ["lifespan", "http", "warmup", "http"]


def test_empty_reindex_body_and_legacy_http_error(monkeypatch) -> None:
    seen = []

    async def fake_reindex(body, runtime, settings):
        seen.append(body)
        return IndexResponse(status="already_ready", source="cache", document_count=1, chunk_count=2)

    monkeypatch.setattr(django_views.rag_routes, "adapter_reindex", fake_reindex)
    response = Client().post("/rag/reindex", data="", content_type="application/json")
    assert response.status_code == 200
    assert response.json()["chunk_count"] == 2
    assert seen == [None]

    async def fake_failed_chat(body, runtime, settings):
        raise ApiError(status_code=503, detail="The service is unavailable.")

    monkeypatch.setattr(django_views.rag_routes, "adapter_chat", fake_failed_chat)
    response = Client().post(
        "/rag/chat", data='{"category":"tax","question":"신고 방법"}',
        content_type="application/json",
    )
    assert response.status_code == 503
    assert response.json()["error"]["retryable"] is True
