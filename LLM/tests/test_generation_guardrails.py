import pytest

from src.data import get_rag_chunks
from src.rag.guardrails import (
    GenerationValidationError,
    is_question_in_scope,
    validate_citation_numbers,
    validate_generated_policy_ids,
    validate_question,
    validate_generated_text,
    validate_policy_citations,
)


def test_citation_numbers_are_deduplicated_in_original_order() -> None:
    assert validate_citation_numbers([2, 1, 2], source_count=2) == (2, 1)


@pytest.mark.parametrize("citations", [[], [0], [3]])
def test_missing_or_invalid_citation_numbers_are_rejected(citations: list[int]) -> None:
    with pytest.raises(GenerationValidationError):
        validate_citation_numbers(citations, source_count=2)


def test_generated_policy_ids_must_exist_in_retrieved_context() -> None:
    assert validate_generated_policy_ids(
        [101, 102],
        retrieved_policy_ids={101, 102},
    ) == (101, 102)

    with pytest.raises(GenerationValidationError, match="not retrieved"):
        validate_generated_policy_ids([999], retrieved_policy_ids={101, 102})


def test_policy_citation_must_point_to_the_same_policy() -> None:
    policy_101_chunk = get_rag_chunks()[0].copy()
    policy_102_chunk = get_rag_chunks()[2].copy()
    policy_101_chunk["score"] = 0.9
    policy_102_chunk["score"] = 0.8

    with pytest.raises(GenerationValidationError, match="another policy"):
        validate_policy_citations(
            101,
            (2,),
            (policy_101_chunk, policy_102_chunk),
        )


def test_blank_generated_text_is_rejected() -> None:
    with pytest.raises(GenerationValidationError, match="must not be blank"):
        validate_generated_text("   ", field_name="answer")


def test_html_space_entity_does_not_create_out_of_scope_clause() -> None:
    question = "업무용 노트북이랑 강의실 인테리어 비용도 경비처리 되나요? &#x20;"

    normalized_question = validate_question(question, max_length=1000)

    assert normalized_question == "업무용 노트북이랑 강의실 인테리어 비용도 경비처리 되나요?"
    assert is_question_in_scope(
        normalized_question,
        allowed_keywords=("경비",),
    )


def test_only_html_whitespace_entities_are_decoded() -> None:
    question = "사업자&nbsp;등록 &#32; 준비 &lt;확인&gt; &amp; &#39; &#65;"

    normalized_question = validate_question(question, max_length=1000)

    assert normalized_question == (
        "사업자 등록   준비 &lt;확인&gt; &amp; &#39; &#65;"
    )
