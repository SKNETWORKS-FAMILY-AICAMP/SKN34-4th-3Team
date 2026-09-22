FROM python:3.13-slim

# 영수증 OCR(글자·위치·신뢰도 추출)용 Tesseract와 한국어 학습 데이터.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Keep the container environment outside /app so the Compose bind mount does
# not hide it during local development.
ENV UV_PROJECT_ENVIRONMENT=/opt/llm-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

EXPOSE 8001

CMD ["uv", "run", "--frozen", "uvicorn", "src.serving.django_config.asgi:application", "--host", "0.0.0.0", "--port", "8001", "--lifespan", "off"]
