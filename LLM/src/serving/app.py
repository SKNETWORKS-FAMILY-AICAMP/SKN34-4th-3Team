from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.config import get_settings
from src.serving.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.serving.rag_routes import (
    RagRuntime,
    adapter_router,
    ocr_router,
    router as rag_router,
)
from src.serving.schemas import ComponentConfiguration, HealthResponse


APP_VERSION = "0.1.0"


def create_app(runtime: RagRuntime | None = None) -> FastAPI:
    """환경설정과 RAG runtime이 연결된 FastAPI 애플리케이션을 생성한다.

    Args:
        runtime: 테스트에서 주입할 선택적 RAG runtime. None이면 빈 runtime을 만든다.

    Returns:
        CORS, 내부 RAG router와 Health endpoint가 등록된 FastAPI 애플리케이션.

    Notes:
        애플리케이션 생성만으로 Embedding 또는 LLM API를 호출하지 않는다.
    """
    settings_config = get_settings()
    fastapi_app = FastAPI(
        title=settings_config.app_name,
        version=APP_VERSION,
        description="Internal LLM and RAG service for grounded explanations.",
    )
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=settings_config.allowed_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    fastapi_app.add_exception_handler(
        StarletteHTTPException,
        http_exception_handler,
    )
    fastapi_app.add_exception_handler(
        RequestValidationError,
        validation_exception_handler,
    )
    fastapi_app.add_exception_handler(Exception, unhandled_exception_handler)
    fastapi_app.state.rag_runtime = runtime or RagRuntime()
    fastapi_app.include_router(rag_router)
    fastapi_app.include_router(adapter_router)
    fastapi_app.include_router(ocr_router)

    @fastapi_app.get(
        "/health",
        response_model=HealthResponse,
        tags=["system"],
        summary="Check whether the LLM API process is running",
    )
    async def health() -> HealthResponse:
        """외부 모델을 호출하지 않고 LLM API 프로세스 상태를 반환한다."""
        return HealthResponse(
            service=settings_config.app_name,
            version=APP_VERSION,
            components=ComponentConfiguration(
                llm=(
                    "configured"
                    if settings_config.llm_configured
                    else "not_configured"
                ),
                embedding=(
                    "configured"
                    if settings_config.embedding_configured
                    else "not_configured"
                ),
                data_source=settings_config.vector_store_backend,
            ),
        )

    return fastapi_app


app = create_app()
