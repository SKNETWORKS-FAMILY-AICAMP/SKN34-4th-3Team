"""HTTP test client that exercises the actual Django URL configuration."""

from __future__ import annotations

import json as jsonlib
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.serving.django_config.settings")

import django
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from src.core.config import Settings, get_settings
from src.serving import django_views
from src.serving.rag_routes import RagRuntime


django.setup()


class DjangoTestClient:
    def __init__(self, runtime: RagRuntime | None = None, settings: Settings | None = None):
        self.runtime = runtime or RagRuntime()
        self.settings = settings or get_settings()
        self.app = SimpleNamespace(state=SimpleNamespace(rag_runtime=self.runtime))
        self._client = Client()

    def _request(self, method: str, path: str, **kwargs):
        django_views.set_runtime(self.runtime)
        with patch.object(django_views, "get_settings", return_value=self.settings):
            return getattr(self._client, method)(path, **kwargs)

    def get(self, path: str, **kwargs):
        return self._request("get", path, **kwargs)

    def options(self, path: str, *, headers: dict | None = None, **kwargs):
        return self._request("options", path, headers=headers or {}, **kwargs)

    def post(self, path: str, *, json: dict | None = None, files: dict | None = None, **kwargs):
        if json is not None:
            return self._request(
                "post", path, data=jsonlib.dumps(json),
                content_type="application/json", **kwargs,
            )
        if files is not None:
            data = {}
            for name, (filename, content, media_type) in files.items():
                data[name] = SimpleUploadedFile(filename, content, content_type=media_type)
            return self._request("post", path, data=data, **kwargs)
        return self._request("post", path, data="", content_type="application/json", **kwargs)
