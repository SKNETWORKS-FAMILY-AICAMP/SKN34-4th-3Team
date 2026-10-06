"""Django ASGI entry point with per-process RAG index warm-up."""

import asyncio
import logging
import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.serving.django_config.settings")
_django_application = get_asgi_application()

from src.core.config import get_settings  # noqa: E402
from src.features import receipt_ocr  # noqa: E402
from src.serving import django_views, rag_routes  # noqa: E402


_logger = logging.getLogger(__name__)
_warmup_task: asyncio.Task | None = None


async def _warm_up() -> None:
    try:
        result = await rag_routes.create_index(
            None, django_views.get_runtime(), get_settings()
        )
        _logger.info("LLM index warm-up %s: chunks=%s", result.status, result.chunk_count)
    except Exception:
        _logger.exception("LLM index warm-up failed")


async def _warm_up_ocr() -> None:
    # 영수증 OCR 모델(PP-OCRv5)을 미리 불러 둔다. 실패해도 OCR 요청 때 Tesseract로 대신한다.
    try:
        ready = await asyncio.to_thread(receipt_ocr.warm_up)
        _logger.info("Receipt OCR warm-up: %s", "PP-OCRv5" if ready else "Tesseract fallback")
    except Exception:
        _logger.exception("Receipt OCR warm-up failed")


async def _warm_up_all() -> None:
    # 원본 문서/BM25 구성과 Paddle 모델 로드의 메모리 피크가 겹치지 않게 한다.
    await _warm_up()
    await _warm_up_ocr()


async def application(scope, receive, send):
    """Start cache-backed indexing on the first HTTP request, using the server loop."""
    global _warmup_task
    if scope["type"] == "http" and _warmup_task is None:
        _warmup_task = asyncio.create_task(_warm_up_all(), name="llm-warmup")
    await _django_application(scope, receive, send)
