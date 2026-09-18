import os
from dataclasses import dataclass

from langsmith import Client

from src.core.config import Settings


class LangSmithConfigurationError(RuntimeError):
    """LangSmith 추적이 활성화됐지만 필수 설정이 없을 때 발생한다."""


@dataclass(frozen=True, slots=True)
class LangSmithRuntime:
    """한 번의 RAG 실행에 적용할 LangSmith 추적 설정을 보관한다."""

    enabled: bool
    project_name: str
    client: Client | None = None


def configure_langsmith(settings: Settings) -> LangSmithRuntime:
    """네트워크 요청 없이 LangSmith 추적 환경과 Client를 준비한다.

    Args:
        settings: LangSmith endpoint, project, API Key와 보안 옵션을 담은 설정.

    Returns:
        추적 활성 여부와 선택적 LangSmith Client를 담은 실행 설정.

    Raises:
        LangSmithConfigurationError: 추적은 활성화됐지만 필수 설정이 없을 때.

    Notes:
        이 함수는 Client만 생성하며 실제 trace 전송은 RAG chain 실행 시 발생한다.
    """
    if not settings.langsmith_tracing:
        os.environ["LANGSMITH_TRACING"] = "false"
        return LangSmithRuntime(enabled=False, project_name=settings.langsmith_project)

    if not settings.langsmith_configured or settings.langsmith_api_key is None:
        raise LangSmithConfigurationError(
            "LangSmith tracing is enabled but LANGSMITH_API_KEY, "
            "LANGSMITH_ENDPOINT, or LANGSMITH_PROJECT is missing."
        )

    langsmith_api_key = settings.langsmith_api_key.get_secret_value()
    os.environ.update(
        {
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_ENDPOINT": settings.langsmith_endpoint,
            "LANGSMITH_PROJECT": settings.langsmith_project,
            "LANGSMITH_API_KEY": langsmith_api_key,
            "LANGSMITH_HIDE_INPUTS": str(settings.langsmith_hide_inputs).lower(),
            "LANGSMITH_HIDE_OUTPUTS": str(settings.langsmith_hide_outputs).lower(),
        }
    )
    langsmith_client = Client(
        api_url=settings.langsmith_endpoint,
        api_key=langsmith_api_key,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
    )
    return LangSmithRuntime(
        enabled=True,
        project_name=settings.langsmith_project,
        client=langsmith_client,
    )
