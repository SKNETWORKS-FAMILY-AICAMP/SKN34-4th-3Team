import re

from src.data.contracts import VectorSearchResult


INSUFFICIENT_EVIDENCE_ANSWER = (
    "제공된 공식 문서에서 질문에 답할 충분한 근거를 찾지 못했습니다. "
    "질문을 구체화하거나 관련 정책을 선택해 주세요."
)

_CLAUSE_SEPARATOR = re.compile(
    r"(?:그리고|그런데|하지만|또한|게다가|반면에|그러면서|하면서|해주고|알려주고|"
    r"[.!?;\n]+)"
)
_NAMED_HTML_WHITESPACE = re.compile(
    r"&(?:nbsp|ensp|emsp|thinsp|tab|newline);",
    re.IGNORECASE,
)
_NUMERIC_HTML_ENTITY = re.compile(
    r"&#(?P<value>x[0-9a-f]+|[0-9]+);",
    re.IGNORECASE,
)


class RagInputError(ValueError):
    """RAG 요청이 입력값 Guardrail을 위반했을 때 발생한다."""


class GenerationValidationError(ValueError):
    """LLM 구조화 출력이 근거 기반 생성 규칙을 위반했을 때 발생한다."""


def validate_question(question: str, *, max_length: int) -> str:
    """질문의 HTML 엔티티·공백과 길이를 검증하고 정규화한 문자열을 반환한다.

    Args:
        question: 사용자가 입력한 원본 질문.
        max_length: 허용할 최대 문자 수.

    Returns:
        앞뒤 공백을 제거한 질문.

    Raises:
        RagInputError: 질문이 비었거나 최대 길이를 초과했을 때.
    """
    normalized_question = _normalize_html_whitespace(question).strip()
    if not normalized_question:
        raise RagInputError("question must not be blank")
    if len(normalized_question) > max_length:
        raise RagInputError(f"question must not exceed {max_length} characters")
    return normalized_question


def _normalize_html_whitespace(value: str) -> str:
    """HTML 엔티티 중 실제 공백 문자만 일반 공백으로 변환한다."""
    named_normalized = _NAMED_HTML_WHITESPACE.sub(" ", value)

    def replace_numeric_entity(match: re.Match[str]) -> str:
        encoded_value = match.group("value")
        base = 16 if encoded_value.casefold().startswith("x") else 10
        digits = encoded_value[1:] if base == 16 else encoded_value
        try:
            character = chr(int(digits, base))
        except (ValueError, OverflowError):
            return match.group(0)
        return " " if character.isspace() else match.group(0)

    return _NUMERIC_HTML_ENTITY.sub(replace_numeric_entity, named_normalized)


def validate_top_k(top_k: int) -> int:
    """검색 결과 개수가 API 허용 범위인지 검사한다.

    Args:
        top_k: Vector Search에서 반환할 최대 Chunk 개수.

    Returns:
        검증이 완료된 top_k.

    Raises:
        RagInputError: top_k가 1~20 범위를 벗어났을 때.
    """
    if not 1 <= top_k <= 20:
        raise RagInputError("top_k must be between 1 and 20")
    return top_k


def has_blocked_keyword(
    question: str,
    *,
    blocked_keywords: tuple[str, ...],
) -> bool:
    """질문에 차단 키워드가 하나라도 포함됐는지 검사한다.

    Args:
        question: 검사할 사용자 질문.
        blocked_keywords: 질문 전체에 하나라도 포함되면 차단할 키워드.

    Returns:
        차단 키워드가 하나라도 포함되면 True, 아니면 False.
    """
    normalized_question = question.casefold()
    return any(
        keyword.casefold() in normalized_question for keyword in blocked_keywords
    )


def is_question_in_scope(
    question: str,
    *,
    allowed_keywords: tuple[str, ...],
    blocked_keywords: tuple[str, ...] = (),
) -> bool:
    """질문의 모든 절이 정책·세무 서비스 범위에 포함되는지 검사한다.

    Args:
        question: 범위를 검사할 정규화된 사용자 질문.
        allowed_keywords: 각 질문 절에 하나 이상 포함돼야 하는 허용 키워드.
        blocked_keywords: 질문 전체에 하나라도 포함되면 차단할 키워드.

    Returns:
        차단 키워드가 없고 모든 질문 절이 허용 범위이면 True, 아니면 False.

    Notes:
        현재 키워드 기반 검사는 실제 평가 데이터가 확보되기 전의 임시 구현이다.
    """
    normalized_question = question.casefold()
    if has_blocked_keyword(question, blocked_keywords=blocked_keywords):
        return False

    question_clauses = [
        clause.strip() for clause in _CLAUSE_SEPARATOR.split(normalized_question)
    ]
    non_empty_clauses = [clause for clause in question_clauses if clause]
    return bool(non_empty_clauses) and all(
        any(keyword.casefold() in clause for keyword in allowed_keywords)
        for clause in non_empty_clauses
    )


def keep_grounded_results(
    results: list[VectorSearchResult],
    *,
    policy_id: int | None,
    min_score: float,
) -> list[VectorSearchResult]:
    """정책 필터와 최소 관련성 점수를 통과한 검색 결과만 유지한다.

    Args:
        results: 관련성 순서로 정렬된 Vector Search 결과.
        policy_id: 상세 검색 대상 정책 ID. None이면 정책 필터를 적용하지 않는다.
        min_score: 답변 근거로 사용할 최소 유사도 점수.

    Returns:
        입력 순서를 유지하면서 두 조건을 모두 통과한 검색 결과 목록.
    """
    return [
        search_result
        for search_result in results
        if search_result["score"] >= min_score
        and (policy_id is None or search_result["policy_id"] == policy_id)
    ]


def validate_generated_text(generated_text: str, *, field_name: str) -> str:
    """LLM이 생성한 필수 문자열이 비어 있지 않은지 검사한다.

    Args:
        generated_text: 구조화 출력에서 검증할 문자열.
        field_name: 오류 메시지에서 식별할 구조화 출력 필드명.

    Returns:
        앞뒤 공백을 제거한 생성 문자열.

    Raises:
        GenerationValidationError: 생성 문자열이 비어 있거나 공백뿐일 때.
    """
    normalized_text = generated_text.strip()
    if not normalized_text:
        raise GenerationValidationError(f"{field_name} must not be blank")
    return normalized_text


def validate_citation_numbers(
    cited_source_numbers: list[int],
    *,
    source_count: int,
) -> tuple[int, ...]:
    """LLM 출처 번호의 범위를 검증하고 중복을 제거한다.

    Args:
        cited_source_numbers: LLM 구조화 출력에 포함된 출처 번호 목록.
        source_count: Prompt에 실제 포함된 검색 근거 개수.

    Returns:
        최초 등장 순서를 유지하면서 중복을 제거한 출처 번호 tuple.

    Raises:
        GenerationValidationError: 출처가 없거나 실제 범위를 벗어난 번호가 있을 때.
        ValueError: source_count가 음수일 때.
    """
    if source_count < 0:
        raise ValueError("source_count must not be negative")

    unique_source_numbers = tuple(dict.fromkeys(cited_source_numbers))
    if not unique_source_numbers:
        raise GenerationValidationError("At least one source citation is required")

    invalid_source_numbers = [
        source_number
        for source_number in unique_source_numbers
        if not 1 <= source_number <= source_count
    ]
    if invalid_source_numbers:
        raise GenerationValidationError(
            f"Invalid source numbers: {invalid_source_numbers}"
        )
    return unique_source_numbers


def validate_generated_policy_ids(
    generated_policy_ids: list[int],
    *,
    retrieved_policy_ids: set[int],
) -> tuple[int, ...]:
    """LLM이 검색 결과에 없는 policy_id를 생성하지 않았는지 검사한다.

    Args:
        generated_policy_ids: 정책 탐색 구조화 출력의 policy_id 목록.
        retrieved_policy_ids: Prompt에 포함된 Chunk에서 확인한 실제 policy_id 집합.

    Returns:
        중복이 없는 검증된 policy_id tuple.

    Raises:
        GenerationValidationError: 정책이 없거나 검색되지 않은 ID가 포함됐을 때.
    """
    unique_policy_ids = tuple(dict.fromkeys(generated_policy_ids))
    if not unique_policy_ids:
        raise GenerationValidationError("At least one generated policy is required")
    if len(unique_policy_ids) != len(generated_policy_ids):
        raise GenerationValidationError("Generated policy IDs must not be duplicated")

    unknown_policy_ids = [
        policy_id
        for policy_id in unique_policy_ids
        if policy_id not in retrieved_policy_ids
    ]
    if unknown_policy_ids:
        raise GenerationValidationError(
            f"Generated policy IDs were not retrieved: {unknown_policy_ids}"
        )
    return unique_policy_ids


def validate_policy_citations(
    policy_id: int,
    citation_numbers: tuple[int, ...],
    retrieved_chunks: tuple[VectorSearchResult, ...],
) -> None:
    """정책 요약의 출처 번호가 동일한 policy_id의 Chunk를 가리키는지 검사한다.

    Args:
        policy_id: 구조화 출력에서 검증된 정책 ID.
        citation_numbers: 범위 검증과 중복 제거가 끝난 출처 번호.
        retrieved_chunks: Prompt에 번호 순서대로 포함된 실제 Chunk.

    Raises:
        GenerationValidationError: 다른 정책의 Chunk를 출처로 사용했을 때.
    """
    invalid_citations = [
        source_number
        for source_number in citation_numbers
        if retrieved_chunks[source_number - 1]["policy_id"] != policy_id
    ]
    if invalid_citations:
        raise GenerationValidationError(
            f"Policy {policy_id} used citations from another policy: "
            f"{invalid_citations}"
        )
