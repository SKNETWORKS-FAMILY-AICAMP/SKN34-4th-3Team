"""Django ASGI entry point with per-process RAG index warm-up."""

import asyncio
import logging
import os

from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.serving.django_config.settings")
_django_application = get_asgi_application()

from src.core.config import get_settings  # noqa: E402
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


async def application(scope, receive, send):
    """Start cache-backed indexing on the first HTTP request, using the server loop."""
    global _warmup_task
    if scope["type"] == "http" and _warmup_task is None:
        _warmup_task = asyncio.create_task(_warm_up(), name="llm-index-warmup")
    await _django_application(scope, receive, send)
