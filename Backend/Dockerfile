FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Keep the container environment outside /app so the Compose bind mount does
# not hide it during local development.
ENV UV_PROJECT_ENVIRONMENT=/opt/backend-venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY . .
RUN uv sync --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
