import uvicorn

from src.core.config import get_settings


def main() -> None:
    """Run the development server without duplicating runtime settings."""
    settings = get_settings()
    uvicorn.run(
        "src.serving.django_config.asgi:application",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        lifespan="off",
    )


if __name__ == "__main__":
    main()
