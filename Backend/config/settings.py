import os

from core.config import BACKEND_ROOT, TOKEN_SECRET

BASE_DIR = BACKEND_ROOT
SECRET_KEY = TOKEN_SECRET
DEBUG = os.getenv("DJANGO_DEBUG", "").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = ["corsheaders"]
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]
CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "config.urls"
# Ninja의 /docs(Swagger) 페이지 렌더링용
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates"}]
APPEND_SLASH = False

# raw SQL(core/db.py)로 Postgres에 직접 접속하므로 Django ORM DB는 쓰지 않는다.
DATABASES = {}

# 영수증 이미지(4MB 제한)는 api/expenses.py에서 검사한다. 그보다 커도 413을 돌려줄 수 있게 여유를 둔다.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

USE_TZ = False
