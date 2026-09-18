import asyncio
from collections.abc import Callable

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langsmith import traceable, tracing_context
from pydantic import ValidationError

from src.core.config import Settings
from src.core.langsmith import configure_langsmith
from src.rag.chain import (
    compact_grounded_answer,
    format_grounded_answer,
    generate_answer,
)
from src.rag.contracts import EligibilityDecision, RagAnswer, SourceCitation
from src.rag.context_builder import (
    build_prompt_context,
    select_chunks_by_source_numbers,
)
from src.rag.guardrails import (
    GenerationValidationError,
    INSUFFICIENT_EVIDENCE_ANSWER,
    is_question_in_scope,
    validate_citation_numbers,
    validate_generated_text,
    validate_question,
    validate_top_k,
)
from src.rag.retriever import retrieve_relevant_chunks
from src.vectorstores.base import VectorSearch


class RagService:
    """특정 정책 검색·Guardrail·판정 보존·답변 생성을 조합한다."""

    def __init__(
        self,
        *,
        vector_search: VectorSearch,
        llm_factory: Callable[[], BaseChatModel],
        settings: Settings,
    ) -> None:
        """특정 정책 RAG 서비스의 의존성을 초기화한다.

        Args:
            vector_search: 관련 정책 Chunk를 검색할 구현체.
            llm_factory: 근거가 있을 때만 채팅 모델을 생성할 함수.
            settings: 검색 임계값, Guardrail과 LangSmith 설정.
        """
        self._vector_search = vector_search
        self._llm_factory = llm_factory
        self._settings = settings

    async def answer(
        self,
        question: str,
        *,
        policy_id: int | None = None,
        top_k: int | None = None,
        decision: EligibilityDecision | None = None,
    ) -> RagAnswer:
        """특정 정책 질문에 근거 기반 답변을 생성한다.

        Args:
            question: 사용자가 입력한 특정 정책 질문.
            policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 문서를 검색한다.
            top_k: 검색할 최대 Chunk 개수. None이면 설정 기본값을 사용한다.
            decision: Backend가 확정한 선택적 자격 판정 결과.

        Returns:
            답변, 출처, 판정 보존값과 Guardrail 차단 사유를 담은 결과.

        Raises:
            RagInputError: 질문 또는 top_k가 허용 범위를 벗어났을 때.
            LangSmithConfigurationError: tracing 설정이 불완전할 때.
        """
        normalized_question = validate_question(
            question,
            max_length=self._settings.max_question_length,
        )
        result_limit = validate_top_k(
            top_k if top_k is not None else self._settings.default_top_k
        )
        if not is_question_in_scope(
            normalized_question,
            allowed_keywords=self._settings.allowed_rag_keywords,
            blocked_keywords=self._settings.blocked_rag_keywords,
        ):
            return RagAnswer(
                answer=self._settings.out_of_scope_answer,
                grounded=False,
                sources=(),
                decision=decision,
                guardrail_reason="out_of_scope",
            )
        langsmith_runtime = configure_langsmith(self._settings)

        with tracing_context(
            project_name=langsmith_runtime.project_name,
            tags=["rag", "in-memory"],
            metadata={"policy_id": policy_id},
            enabled=langsmith_runtime.enabled,
            client=langsmith_runtime.client,
        ):
            return await self._answer_traced(
                normalized_question,
                policy_id=policy_id,
                top_k=result_limit,
                decision=decision,
            )

    @traceable(name="rag_answer", run_type="chain")
    async def _answer_traced(
        self,
        question: str,
        *,
        policy_id: int | None,
        top_k: int,
        decision: EligibilityDecision | None,
    ) -> RagAnswer:
        """검색부터 LLM 생성까지 LangSmith 하위 trace로 실행한다.

        Args:
            question: 입력 검증과 범위 검사를 통과한 사용자 질문.
            policy_id: 검색을 제한할 선택적 정책 ID.
            top_k: Retriever가 반환할 최대 Chunk 개수.
            decision: 변경 없이 답변과 응답에 반영할 Backend 판정 결과.

        Returns:
            근거가 없으면 차단 결과, 있으면 LLM 답변과 출처를 담은 결과.
        """
        relevant_chunks = await asyncio.to_thread(
            retrieve_relevant_chunks,
            self._vector_search,
            question,
            policy_id=policy_id,
            top_k=top_k,
            min_score=self._settings.min_relevance_score,
        )
        if not relevant_chunks:
            return RagAnswer(
                answer=INSUFFICIENT_EVIDENCE_ANSWER,
                grounded=False,
                sources=(),
                decision=decision,
                guardrail_reason="insufficient_evidence",
            )

        prompt_context = build_prompt_context(
            relevant_chunks,
            max_context_characters=self._settings.max_context_characters,
            max_chunks_per_policy=self._settings.max_chunks_per_policy,
        )
        try:
            structured_answer = await generate_answer(
                self._llm_factory(),
                question=question,
                prompt_context=prompt_context,
                decision=decision,
            )
            structured_answer = compact_grounded_answer(structured_answer)
            validate_generated_text(structured_answer.answer, field_name="answer")
            citation_numbers = validate_citation_numbers(
                structured_answer.cited_source_numbers,
                source_count=len(prompt_context.selected_chunks),
            )
        except (GenerationValidationError, OutputParserException, ValidationError):
            return RagAnswer(
                answer=self._settings.invalid_generation_answer,
                grounded=False,
                sources=(),
                decision=decision,
                guardrail_reason="generation_validation_failed",
            )

        cited_chunks = select_chunks_by_source_numbers(
            prompt_context,
            citation_numbers,
        )
        source_citations = tuple(
            SourceCitation.from_search_result(cited_chunk)
            for cited_chunk in cited_chunks
        )
        return RagAnswer(
            answer=format_grounded_answer(structured_answer),
            grounded=bool(source_citations),
            sources=source_citations,
            decision=decision,
            guardrail_reason=None,
        )
