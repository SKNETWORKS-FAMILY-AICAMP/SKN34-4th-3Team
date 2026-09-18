import asyncio

from src.data import get_rag_chunks, get_user_profile
from src.rag.chain import generate_answer, generate_policy_summary
from src.rag.context_builder import PromptContext, build_prompt_context
from src.rag.contracts import (
    GeneratedGroundedAnswer,
    GeneratedPolicyDiscovery,
)
from src.rag.prompts import (
    DECISION_EXPLANATION_PROMPT_VERSION,
    POLICY_DISCOVERY_PROMPT,
    POLICY_DISCOVERY_PROMPT_VERSION,
)
from tests.fakes import make_discovery_fake_model, make_grounded_fake_model


def make_prompt_context() -> PromptContext:
    """구조화 Chain 테스트에 사용할 검색 문맥을 생성한다."""
    retrieved_chunk = get_rag_chunks()[0].copy()
    retrieved_chunk["score"] = 0.9
    return build_prompt_context(
        [retrieved_chunk],
        max_context_characters=10000,
        max_chunks_per_policy=2,
    )


def test_grounded_chain_returns_schema_and_prompt_boundaries() -> None:
    chat_model = make_grounded_fake_model()

    generated_answer = asyncio.run(
        generate_answer(
            chat_model,
            question="지원 대상을 알려줘",
            prompt_context=make_prompt_context(),
            decision=None,
        )
    )

    assert isinstance(generated_answer, GeneratedGroundedAnswer)
    assert "<backend_decision>" in chat_model.last_prompt_text
    assert "<retrieved_documents>" in chat_model.last_prompt_text
    assert "<user_question>" in chat_model.last_prompt_text
    assert chat_model.last_config is not None
    assert (
        chat_model.last_config["metadata"]["prompt_version"]
        == DECISION_EXPLANATION_PROMPT_VERSION
    )


def test_policy_discovery_chain_uses_profile_boundary_and_version() -> None:
    chat_model = make_discovery_fake_model(
        [
            {
                "policy_id": 101,
                "summary": "정책 요약",
                "relevance_reasons": ["창업 관련"],
                "requirements_to_verify": [],
                "cited_source_numbers": [1],
            }
        ]
    )

    generated_discovery = asyncio.run(
        generate_policy_summary(
            chat_model,
            question="관련 정책을 알려줘",
            user=get_user_profile(1),
            prompt_context=make_prompt_context(),
        )
    )

    assert isinstance(generated_discovery, GeneratedPolicyDiscovery)
    assert "<user_profile>" in chat_model.last_prompt_text
    assert "<retrieved_documents>" in chat_model.last_prompt_text
    assert chat_model.last_config is not None
    assert (
        chat_model.last_config["metadata"]["prompt_version"]
        == POLICY_DISCOVERY_PROMPT_VERSION
    )


def test_policy_discovery_prompt_only_requires_supplied_chain_variables() -> None:
    assert set(POLICY_DISCOVERY_PROMPT.input_variables) == {
        "document_context",
        "question",
        "user_context",
    }
