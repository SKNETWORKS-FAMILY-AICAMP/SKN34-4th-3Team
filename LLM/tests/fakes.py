from collections.abc import Mapping
from typing import Any

from langchain_core.prompt_values import PromptValue
from langchain_core.runnables import RunnableConfig, RunnableLambda
from pydantic import BaseModel

from src.rag.contracts import (
    GeneratedGroundedAnswer,
    GeneratedPolicyDiscovery,
)
from src.rag.answer import UnifiedAnswerResult
from src.rag.graph import RouteDecision
from src.rag.tax import TaxIntentDecision


class FakeStructuredChatModel:
    """외부 API 없이 Pydantic 구조화 출력을 반환하는 테스트 모델."""

    def __init__(
        self,
        outputs_by_schema: Mapping[type[BaseModel], dict[str, Any]],
    ) -> None:
        """구조화 schema별 반환값을 저장한다.

        Args:
            outputs_by_schema: Pydantic schema를 key, 검증할 Dictionary를 value로
                갖는 테스트 출력 mapping.
        """
        self._outputs_by_schema = dict(outputs_by_schema)
        self.call_count = 0
        self.last_prompt_text = ""
        self.last_config: RunnableConfig | None = None
        self.bound_kwargs: dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "FakeStructuredChatModel":
        """호출별 모델 옵션을 기록하고 같은 Fake 모델을 반환한다."""
        self.bound_kwargs.update(kwargs)
        return self

    def with_structured_output(
        self,
        schema: type[BaseModel],
        **_kwargs: object,
    ) -> RunnableLambda:
        """요청받은 schema로 Fake 출력을 검증하는 Runnable을 반환한다.

        Args:
            schema: 실제 모델의 구조화 출력과 동일하게 검증할 Pydantic 모델.
            **_kwargs: 실제 LangChain 메서드와 호환하기 위한 미사용 옵션.

        Returns:
            Prompt 입력을 받으면 검증된 Pydantic 객체를 반환하는 Runnable.
        """

        async def return_structured_output(
            prompt_input: PromptValue,
            config: RunnableConfig,
        ) -> BaseModel:
            self.call_count += 1
            self.last_prompt_text = prompt_input.to_string()
            self.last_config = config
            return schema.model_validate(self._outputs_by_schema[schema])

        return RunnableLambda(return_structured_output)


def make_grounded_fake_model(
    answer: str = "테스트 근거 답변입니다.",
    cited_source_numbers: list[int] | None = None,
) -> FakeStructuredChatModel:
    """특정 정책 답변용 Fake 구조화 모델을 생성한다."""
    return FakeStructuredChatModel(
        {
            GeneratedGroundedAnswer: {
                "answer": answer,
                "cited_source_numbers": cited_source_numbers or [1],
                "limitations": [],
            }
        }
    )


def make_discovery_fake_model(
    policies: list[dict[str, Any]],
    *,
    overview: str = "사용자 조건과 관련된 정책을 찾았습니다.",
) -> FakeStructuredChatModel:
    """사용자 기반 정책 탐색용 Fake 구조화 모델을 생성한다."""
    return FakeStructuredChatModel(
        {
            GeneratedPolicyDiscovery: {
                "overview": overview,
                "policies": policies,
                "limitations": ["최종 자격은 별도 확인이 필요합니다."],
            }
        }
    )


def make_default_fake_model() -> FakeStructuredChatModel:
    """API 테스트의 두 구조화 출력 schema를 모두 지원하는 Fake 모델을 만든다."""
    return FakeStructuredChatModel(
        {
            RouteDecision: {
                "route": "policy",
                "personalized": False,
            },
            TaxIntentDecision: {
                "calculation_required": False,
                "calculation_type": None,
                "reason": "법률 설명 질문",
            },
            UnifiedAnswerResult: {
                "answer": "테스트 근거 답변입니다.",
                "status": "success",
                "cited_source_numbers": [1],
            },
            GeneratedGroundedAnswer: {
                "answer": "테스트 근거 답변입니다.",
                "cited_source_numbers": [1],
                "limitations": [],
            },
            GeneratedPolicyDiscovery: {
                "overview": "사용자 조건과 관련된 정책을 찾았습니다.",
                "policies": [
                    {
                        "policy_id": 120,
                        "summary": "청년 전월세보증금 이자지원 정책 요약입니다.",
                        "relevance_reasons": ["청년 지원과 관련됨"],
                        "requirements_to_verify": ["세부 자격 확인"],
                        "cited_source_numbers": [1],
                    }
                ],
                "limitations": ["최종 자격은 별도 확인이 필요합니다."],
            },
        }
    )
