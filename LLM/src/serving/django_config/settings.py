"""Minimal Django settings: RAG data access remains in src.core/database."""

import os

from src.core.config import get_settings


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "llm-api-no-django-sessions")
DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,llm,testserver").split(",")
    if host.strip()
]
ROOT_URLCONF = "src.serving.django_config.urls"
INSTALLED_APPS = ["corsheaders"]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]
CORS_ALLOWED_ORIGINS = get_settings().allowed_cors_origins
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_METHODS = ["GET", "POST", "OPTIONS"]
CORS_ALLOW_HEADERS = ["content-type"]
APPEND_SLASH = False
DATABASES = {}
USE_TZ = False
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
