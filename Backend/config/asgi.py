import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

# FastAPI lifespan 대체. manage.py check·테스트에서 DB 접속을 피하려고 서버 진입점에서만 호출한다.
from config.api import startup  # noqa: E402

startup()
