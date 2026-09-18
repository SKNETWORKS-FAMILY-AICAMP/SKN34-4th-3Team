import uvicorn

from src.core.config import get_settings
from src.serving.app import app


def main() -> None:
    """Run the development server without duplicating runtime settings."""
    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


if __name__ == "__main__":
    main()
