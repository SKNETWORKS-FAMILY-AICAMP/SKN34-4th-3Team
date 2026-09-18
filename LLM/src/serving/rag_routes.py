import asyncio
import base64
from collections.abc import Callable
from functools import partial
from threading import RLock
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph.state import CompiledStateGraph
from starlette.concurrency import run_in_threadpool

from src.core.config import Settings, get_settings
from src.core.database import DatabaseConfigurationError
from src.core.langsmith import LangSmithConfigurationError
from src.data import MockDataNotFoundError, get_document_catalog
from src.data.mock_repository import get_user_profile as get_mock_user_profile
from src.data.postgres_repository import (
    DatabaseDataNotFoundError,
    get_user_profile as get_database_user_profile,
)
from src.features.document_processing import PdfDocumentError
from src.features.indexing import (
    load_or_build_document_index,
    load_or_build_postgres_index,
)
from src.models import ModelConfigurationError, get_embedding_model, get_llm
from src.rag.contracts import EligibilityDecision, SourceCitation
from src.rag.backend_tasks import (
    extract_receipt,
    generate_deductibility,
    generate_legal_basis,
    summarize_announcement,
)
from src.rag.discovery import PolicyDiscoveryService
from src.rag.graph import GraphState, build_graph
from src.rag.guardrails import RagInputError, validate_question, validate_top_k
from src.rag.reranker import CohereRerankError, rerank_documents
from src.rag.roadmap import RoadmapStep
from src.rag.tax import merge_evidence, parse_exact_legal_query
from src.rag.tax_cache import TaxRagCache
from src.serving.schemas import (
    AnnouncementSummaryRequest,
    AnnouncementSummaryResponse,
    BackendUserContext,
    DeductibilityRequest,
    DeductibilityResponse,
    EligibilityDecisionRequest,
    IndexRequest,
    IndexResponse,
    LegalBasisRequest,
    LegalBasisResponse,
    MatchedPolicyResponse,
    PolicyRecommendationRequest,
    PolicyRecommendationResponse,
    RagAnswerRequest,
    RagAnswerResponse,
    RagChatRequest,
    RagChatResponse,
    RagChatSource,
    RagReindexRequest,
    ReadyResponse,
    ReceiptExtractionResponse,
    SourceResponse,
)
from src.serving.errors import upstream_http_exception
from src.vectorstores.base import VectorSearch
from src.vectorstores.hybrid import HybridSearch
from src.vectorstores.postgres import PostgresVectorSearch, RagDocumentNotFoundError


class RagIndexNotReadyError(RuntimeError):
    """프로세스 내부 RAG 인덱스 준비 전에 답변을 요청할 때 발생한다."""


class RagRuntime:
    """FastAPI 프로세스의 RAG 인덱스와 모델 생성 함수를 관리한다."""

    def __init__(
        self,
        *,
        embedding_factory: Callable[[], Embeddings] = get_embedding_model,
        llm_factory: Callable[[], BaseChatModel] = get_llm,
        notice_search: Callable[[GraphState], list[dict[str, object]]] | None = None,
    ) -> None:
        """모델 팩토리와 비어 있는 RAG 실행 상태를 초기화한다.

        Args:
            embedding_factory: 인덱싱 시 Embedding 모델을 생성할 함수.
            llm_factory: 근거가 확보된 답변 생성 시 채팅 모델을 생성할 함수.
        """
        self.embedding_factory = embedding_factory
        self._llm_factory = llm_factory
        self._llm: BaseChatModel | None = None
        self.notice_search = notice_search
        self.index_lock = asyncio.Lock()
        self._cache_lock = RLock()
        self._vector_search: VectorSearch | None = None
        self._hybrid_search: HybridSearch | None = None
        self._hybrid_settings: Settings | None = None
        self._graph: CompiledStateGraph | None = None
        self._graph_settings: Settings | None = None
        self._graph_notice_search: Callable[[GraphState], list[dict[str, object]]] | None = None
        self.document_count = 0
        self.chunk_count = 0
        self.index_source: Literal["cache", "embedding"] | None = None

    @property
    def ready(self) -> bool:
        """프로세스 메모리에 검색 가능한 인덱스가 있으면 True를 반환한다."""
        return self._vector_search is not None

    def set_index(
        self,
        vector_search: VectorSearch,
        *,
        document_count: int,
        chunk_count: int,
        index_source: Literal["cache", "embedding"],
    ) -> None:
        """검색 인덱스와 문서 수를 현재 프로세스 상태로 저장한다.

        Args:
            vector_search: 검색 가능한 In-memory Vector Search 구현체.
            document_count: 인덱스에 반영된 원본 문서 개수.
            chunk_count: 인덱스에 저장된 RAG Chunk 개수.
            index_source: 로컬 캐시 또는 신규 Embedding 중 인덱스 생성 출처.
        """
        with self._cache_lock:
            self._vector_search = vector_search
            self.document_count = document_count
            self.chunk_count = chunk_count
            self.index_source = index_source
            self._hybrid_search = None
            self._graph = None

    def llm_factory(self) -> BaseChatModel:
        with self._cache_lock:
            if self._llm is None:
                self._llm = self._llm_factory()
            return self._llm

    def require_index(self) -> VectorSearch:
        """준비된 Vector Search를 반환하고 없으면 명확한 예외를 발생시킨다.

        Returns:
            현재 FastAPI 프로세스에 적재된 VectorSearch 구현체.

        Raises:
            RagIndexNotReadyError: 인덱스를 아직 준비하지 않았을 때.
        """
        if self._vector_search is None:
            raise RagIndexNotReadyError(
                "RAG index is not ready. Call POST /internal/rag/index first."
            )
        return self._vector_search

    def require_hybrid_index(self, settings: Settings) -> HybridSearch:
        """준비된 Dense 인덱스를 기존 BM25·RRF 검색과 결합해 반환한다."""
        with self._cache_lock:
            if self._hybrid_search is None or self._hybrid_settings is not settings:
                vector_search = self.require_index()
                self._hybrid_search = (
                    vector_search if isinstance(vector_search, HybridSearch) else HybridSearch(
                        dense_search=vector_search,
                        chunks=vector_search.get_chunks(),
                        dense_candidate_k=settings.hybrid_dense_candidate_k,
                        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
                        rrf_k=settings.hybrid_rrf_k,
                    )
                )
                self._hybrid_settings = settings
            return self._hybrid_search

    def require_graph(
        self,
        settings: Settings,
        notice_search: Callable[[GraphState], list[dict[str, object]]] | None,
    ) -> CompiledStateGraph:
        with self._cache_lock:
            if (
                self._graph is None
                or self._graph_settings is not settings
                or self._graph_notice_search is not notice_search
            ):
                hybrid_search = self.require_hybrid_index(settings) if self.ready else None
                vector_search = self.require_index() if self.ready else None
                dense_search = (
                    vector_search.dense_search
                    if isinstance(vector_search, HybridSearch)
                    else vector_search
                )
                tax_cache = (
                    TaxRagCache(settings, self.embedding_factory(), dense_search)
                    if settings.tax_cache_enabled
                    and isinstance(dense_search, PostgresVectorSearch)
                    else None
                )
                self._graph = build_graph(
                    self.llm_factory(),
                    policy_search=hybrid_search,
                    tax_search=hybrid_search,
                    tax_cache=tax_cache,
                    notice_search=notice_search,
                    settings=settings,
                )
                self._graph_settings = settings
                self._graph_notice_search = notice_search
            return self._graph


router = APIRouter(prefix="/internal/rag", tags=["internal-rag"])
adapter_router = APIRouter(prefix="/rag", tags=["backend-adapter"])
ocr_router = APIRouter(prefix="/ocr", tags=["backend-adapter"])

MAX_RECEIPT_BYTES = 4 * 1024 * 1024
SUPPORTED_RECEIPT_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}


def get_runtime(request: Request) -> RagRuntime:
    """현재 FastAPI 애플리케이션의 RAG runtime을 반환한다.

    Args:
        request: 애플리케이션 상태에 접근할 FastAPI 요청 객체.

    Returns:
        프로세스 내부 Vector 인덱스를 관리하는 RagRuntime.
    """
    return request.app.state.rag_runtime


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> ReadyResponse:
    """외부 API 호출 없이 RAG 인덱스와 모델 설정 상태를 반환한다.

    Args:
        rag_runtime: 현재 프로세스의 인덱스 상태를 보관하는 runtime.
        settings_config: LLM, Embedding과 LangSmith 설정.

    Returns:
        인덱스 준비 여부, 모델 설정 상태와 문서·Chunk 수.
    """
    return ReadyResponse(
        status="ready" if rag_runtime.ready else "not_ready",
        index_ready=rag_runtime.ready,
        llm_configured=settings_config.llm_configured,
        embedding_configured=settings_config.embedding_configured,
        langsmith_tracing=settings_config.langsmith_configured,
        document_count=rag_runtime.document_count,
        chunk_count=rag_runtime.chunk_count,
        index_source=rag_runtime.index_source,
    )


@router.post("/index", response_model=IndexResponse)
async def create_index(
    request_body: IndexRequest | None = None,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> IndexResponse:
    """로컬 캐시를 우선 사용해 현재 프로세스의 RAG 인덱스를 준비한다.

    Args:
        request_body: 유효한 캐시를 무시할지 지정하는 선택적 요청 본문.
        rag_runtime: 인덱스와 모델 팩토리를 보관하는 현재 프로세스 runtime.
        settings_config: 캐시 경로, 모델명과 Chunk 설정.

    Returns:
        인덱스 상태, 생성 출처와 문서·Chunk 수.

    Raises:
        HTTPException: 설정 누락, PDF 처리 또는 Embedding 요청에 실패했을 때.
    """
    return await _prepare_index(
        force=request_body.force if request_body is not None else False,
        document_ids=[],
        allow_ready_shortcut=True,
        rag_runtime=rag_runtime,
        settings=settings_config,
    )


@router.post("/answer", response_model=RagAnswerResponse)
async def answer(
    request_body: RagAnswerRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> RagAnswerResponse:
    """사용자 질문을 LangGraph의 Policy·Notice·Tax 흐름으로 처리한다.

    Args:
        request_body: 질문, 선택적 정책 ID, top-k와 Backend 판정 결과.
        rag_runtime: 준비된 Vector Search와 LLM 팩토리를 제공하는 runtime.
        settings_config: 검색·Guardrail·LangSmith 설정.

    Returns:
        근거 기반 답변, 출처, 판정 보존값과 Guardrail 사유.

    Raises:
        HTTPException: 인덱스 미준비, 입력 오류 또는 외부 모델 호출 실패 시.
    """
    try:
        graph_result = await _execute_graph(
            question=request_body.question,
            category=None,
            policy_id=request_body.policy_id,
            top_k=request_body.top_k,
            decision=_to_domain_decision(request_body.decision),
            user_context=_backend_user_context(request_body.user_context),
            conversation_history=[],
            roadmap_step=None,
            user_id=request_body.user_id,
            notice_search=rag_runtime.notice_search,
            rag_runtime=rag_runtime,
            settings=settings_config,
        )
        source_responses = [
            _graph_source_response(source)
            for source in graph_result.get("answer_sources", [])
            if "chunk_id" in source and "content" in source
        ]
        return RagAnswerResponse(
            answer=str(graph_result["answer"]),
            route=graph_result["route"],
            status=graph_result["answer_status"],
            grounded=bool(source_responses),
            sources=source_responses,
            decision=request_body.decision,
            guardrail_reason=(
                graph_result.get("guardrail_reason")
                or _graph_guardrail_reason(str(graph_result["answer_status"]))
            ),
        )
    except RagIndexNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except (MockDataNotFoundError, DatabaseDataNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except RagInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="RAG answer generation failed.",
        ) from exc


@adapter_router.get("/ready", response_model=ReadyResponse)
async def adapter_ready(
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> ReadyResponse:
    """Backend 명세 경로에서 기존 인덱스 준비 상태를 반환한다."""
    return await ready(rag_runtime, settings_config)


@adapter_router.post("/reindex", response_model=IndexResponse)
async def adapter_reindex(
    request_body: RagReindexRequest | None = None,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> IndexResponse:
    """Backend의 명시적 전체 또는 PostgreSQL 부분 재색인 요청을 수행한다."""
    return await _prepare_index(
        force=request_body.force if request_body is not None else False,
        document_ids=request_body.documentIds if request_body is not None else [],
        allow_ready_shortcut=False,
        rag_runtime=rag_runtime,
        settings=settings_config,
    )


async def _prepare_index(
    *,
    force: bool,
    document_ids: list[int],
    allow_ready_shortcut: bool,
    rag_runtime: RagRuntime,
    settings: Settings,
) -> IndexResponse:
    """인덱스 초기 준비와 Backend의 명시적 재색인을 동일 lock에서 처리한다."""
    requested_ids = list(dict.fromkeys(document_ids))
    if any(document_id < 1 for document_id in requested_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="documentIds must contain only positive integers",
        )
    if requested_ids and settings.vector_store_backend != "postgres":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="documentIds partial reindex requires the postgres backend",
        )
    if allow_ready_shortcut and rag_runtime.ready and not force:
        return _index_response(rag_runtime, "already_ready")

    async with rag_runtime.index_lock:
        if allow_ready_shortcut and rag_runtime.ready and not force:
            return _index_response(rag_runtime, "already_ready")
        try:
            embedding_model = rag_runtime.embedding_factory()
            if requested_ids:
                postgres_search = PostgresVectorSearch(
                    embedding=embedding_model,
                    settings=settings,
                )
                processed_ids = await run_in_threadpool(
                    partial(
                        postgres_search.reindex_document_ids,
                        requested_ids,
                        force=force,
                    )
                )
                total_document_count, total_chunk_count = await run_in_threadpool(
                    postgres_search.counts
                )
                runtime_search = _runtime_search(postgres_search, settings)
                index_source: Literal["cache", "embedding"] = (
                    "embedding" if postgres_search.last_embedded_count else "cache"
                )
                rag_runtime.set_index(
                    runtime_search,
                    document_count=total_document_count,
                    chunk_count=total_chunk_count,
                    index_source=index_source,
                )
                return IndexResponse(
                    status=(
                        "ready"
                        if postgres_search.last_embedded_count
                        else "already_ready"
                    ),
                    source=index_source,
                    document_count=len(processed_ids),
                    chunk_count=len(processed_ids),
                    requested_document_ids=processed_ids,
                )

            if settings.vector_store_backend == "postgres":
                cached_vector_index = await run_in_threadpool(
                    partial(
                        load_or_build_postgres_index,
                        embedding=embedding_model,
                        settings=settings,
                        force=force,
                    )
                )
            else:
                document_catalog = get_document_catalog()
                cached_vector_index = await run_in_threadpool(
                    partial(
                        load_or_build_document_index,
                        embedding=embedding_model,
                        settings=settings,
                        catalog=document_catalog,
                        force=force,
                    )
                )
            runtime_search = _runtime_search(
                cached_vector_index.vector_search,
                settings,
            )
            index_source = (
                "cache" if cached_vector_index.loaded_from_cache else "embedding"
            )
            rag_runtime.set_index(
                runtime_search,
                document_count=cached_vector_index.document_count,
                chunk_count=cached_vector_index.chunk_count,
                index_source=index_source,
            )
            return _index_response(
                rag_runtime,
                "already_ready" if cached_vector_index.loaded_from_cache else "ready",
            )
        except RagDocumentNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except (ModelConfigurationError, DatabaseConfigurationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except (FileNotFoundError, PdfDocumentError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise upstream_http_exception(
                exc,
                fallback_message="Document embedding failed.",
            ) from exc


def _runtime_search(vector_search: VectorSearch, settings: Settings) -> VectorSearch:
    """설정에 따라 Dense 검색기를 그대로 쓰거나 Hybrid 검색기로 감싼다."""
    if settings.retrieval_mode != "hybrid":
        return vector_search
    return HybridSearch(
        dense_search=vector_search,
        chunks=vector_search.get_chunks(),
        dense_candidate_k=settings.hybrid_dense_candidate_k,
        bm25_candidate_k=settings.hybrid_bm25_candidate_k,
        rrf_k=settings.hybrid_rrf_k,
    )


@adapter_router.post("/chat", response_model=RagChatResponse)
async def adapter_chat(
    request_body: RagChatRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> RagChatResponse:
    """Backend 사용자 Context와 공고 결과를 LangGraph 입력에 연결한다."""
    try:
        user_context = _backend_user_context(request_body.userContext)
        graph_result = await _execute_graph(
            question=request_body.question,
            category=request_body.category,
            policy_id=None,
            top_k=None,
            decision=None,
            user_context=user_context,
            conversation_history=[
                message.model_dump()
                for message in request_body.conversationHistory
            ],
            roadmap_step=request_body.roadmapStep,
            user_id=None,
            notice_search=(
                (
                    lambda _state: [
                        notice.model_dump(mode="json", exclude_none=True)
                        for notice in request_body.noticeResults or []
                    ]
                )
                if request_body.noticeResults is not None
                else None
            ),
            rag_runtime=rag_runtime,
            settings=settings_config,
        )
        sources = [
            _backend_source(source)
            for source in graph_result.get("answer_sources", [])
        ]
        return RagChatResponse(
            answer=str(graph_result["answer"]),
            sources=sources,
            grounded=bool(sources),
            route=graph_result["route"],
            status=graph_result["answer_status"],
            guardrail_reason=(
                graph_result.get("guardrail_reason")
                or _graph_guardrail_reason(str(graph_result["answer_status"]))
            ),
        )
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except RagInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="RAG chat failed.",
        ) from exc


@adapter_router.post("/legal-basis", response_model=LegalBasisResponse)
async def adapter_legal_basis(
    request_body: LegalBasisRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> LegalBasisResponse:
    """Backend가 확정한 세액감면 판정을 보존하며 법령 근거를 설명한다."""
    reasons = [reason.strip() for reason in request_body.reasons if reason.strip()]
    if not reasons:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="reasons must contain at least one non-blank item",
        )
    conditions = request_body.conditions.model_dump(exclude_none=True)
    query = _legal_basis_query(request_body.eligible, reasons, conditions)
    try:
        evidence = await _retrieve_tax_evidence(
            query,
            rag_runtime=rag_runtime,
            settings=settings_config,
        )
        if not evidence:
            return LegalBasisResponse(
                reasons=reasons,
                legalBasis="현재 확인된 법령 문서에서 판정 근거를 찾지 못했습니다.",
                sources=[],
                grounded=False,
                status="no_result",
                llmUsed=False,
            )
        generated, citations = await generate_legal_basis(
            rag_runtime.llm_factory(),
            eligible=request_body.eligible,
            reasons=reasons,
            conditions=conditions,
            evidence=evidence,
        )
        sources = [_backend_source(evidence[number - 1]) for number in citations]
        return LegalBasisResponse(
            reasons=reasons,
            legalBasis=generated.legal_basis,
            sources=sources,
            grounded=bool(sources),
            status="success",
            llmUsed=True,
        )
    except RagIndexNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="Legal basis generation failed.",
        ) from exc


@adapter_router.post("/deductibility", response_model=DeductibilityResponse)
async def adapter_deductibility(
    request_body: DeductibilityRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> DeductibilityResponse:
    """지출 정보와 Tax RAG 근거로 경비 인정 가능성을 분석한다."""
    category = request_body.category.strip()
    vendor = request_body.vendor.strip()
    if not category or not vendor:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="category and vendor must not be blank",
        )
    expense = {
        "category": category,
        "amount": request_body.amount,
        "vendor": vendor,
        "items": [item.strip() for item in request_body.items if item.strip()],
    }
    query = (
        f"사업 경비 인정 가능성: 카테고리 {category}, 상호 {vendor}, "
        f"금액 {request_body.amount}원, 품목 {', '.join(expense['items']) or '없음'}"
    )
    try:
        evidence = await _retrieve_tax_evidence(
            query,
            rag_runtime=rag_runtime,
            settings=settings_config,
        )
        if not evidence:
            return DeductibilityResponse(
                deductible=False,
                confidence=0,
                basis="현재 확인된 세법 문서만으로는 경비 인정 가능성을 판단할 수 없습니다.",
                sources=[],
                grounded=False,
                status="no_result",
                llmUsed=False,
            )
        generated, citations = await generate_deductibility(
            rag_runtime.llm_factory(),
            expense=expense,
            evidence=evidence,
        )
        sources = [_backend_source(evidence[number - 1]) for number in citations]
        return DeductibilityResponse(
            deductible=generated.deductible,
            confidence=generated.confidence,
            basis=generated.basis,
            sources=sources,
            grounded=bool(sources),
            status="success",
            llmUsed=True,
        )
    except RagIndexNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="Deductibility analysis failed.",
        ) from exc


@adapter_router.post(
    "/summarize-announcement",
    response_model=AnnouncementSummaryResponse,
)
async def adapter_summarize_announcement(
    request_body: AnnouncementSummaryRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> AnnouncementSummaryResponse:
    """Backend가 전달한 공고 원문만 사용해 구조화 요약을 생성한다."""
    try:
        raw_content = validate_question(
            request_body.rawContent,
            max_length=settings_config.max_context_characters,
        )
        generated = await summarize_announcement(
            rag_runtime.llm_factory(),
            raw_content=raw_content,
        )
        return AnnouncementSummaryResponse(
            target=generated.target,
            benefit=generated.benefit,
            period=generated.period,
            documents=generated.documents,
            notes=generated.notes,
            source=request_body.source,
            llmUsed=True,
        )
    except RagInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="Announcement summarization failed.",
        ) from exc


@ocr_router.post("/receipt", response_model=ReceiptExtractionResponse)
async def adapter_receipt_ocr(
    image: UploadFile = File(...),
    rag_runtime: RagRuntime = Depends(get_runtime),
) -> ReceiptExtractionResponse:
    """4 MiB 이하 영수증 이미지를 Vision 구조화 출력으로 추출한다."""
    media_type = (image.content_type or "").casefold()
    if media_type not in SUPPORTED_RECEIPT_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="receipt image must be JPEG, PNG, or WebP",
        )
    raw_image = await image.read(MAX_RECEIPT_BYTES + 1)
    if not raw_image:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="receipt image must not be empty",
        )
    if len(raw_image) > MAX_RECEIPT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="receipt image must not exceed 4 MiB",
        )
    image_data_url = (
        f"data:{media_type};base64,{base64.b64encode(raw_image).decode('ascii')}"
    )
    try:
        generated = await extract_receipt(
            rag_runtime.llm_factory(),
            image_data_url=image_data_url,
        )
        return ReceiptExtractionResponse(
            date=generated.date,
            vendor=generated.vendor.strip() if generated.vendor else None,
            amount=generated.amount,
            items=[item.strip() for item in generated.items if item.strip()],
            category=(
                generated.category.strip() if generated.category else None
            ),
        )
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="Receipt extraction failed.",
        ) from exc


async def _retrieve_tax_evidence(
    query: str,
    *,
    rag_runtime: RagRuntime,
    settings: Settings,
) -> list[dict[str, object]]:
    """준비된 Hybrid 인덱스에서 Tax 문서만 검색하고 선택적으로 재정렬한다."""
    hybrid_search = rag_runtime.require_hybrid_index(settings)
    _, _, rrf_documents = await asyncio.to_thread(
        partial(
            hybrid_search.search_stages,
            query,
            policy_id=None,
            source_types=("tax_document",),
            top_k=settings.cohere_rerank_candidate_k,
        )
    )
    exact_reference = parse_exact_legal_query(query)
    exact_documents = (
        await asyncio.to_thread(
            hybrid_search.search_legal_reference,
            *exact_reference,
            top_k=settings.default_top_k,
        )
        if exact_reference is not None
        else []
    )
    tax_documents = [
        document
        for document in merge_evidence(exact_documents, rrf_documents)
        if document["policy_id"] is None
        and document["score"] >= settings.min_relevance_score
    ]
    if not tax_documents:
        return []
    try:
        return await asyncio.to_thread(
            rerank_documents,
            query,
            tax_documents,
            top_n=settings.default_top_k,
            settings=settings,
        )
    except CohereRerankError:
        return tax_documents[: settings.default_top_k]


def _legal_basis_query(
    eligible: bool,
    reasons: list[str],
    conditions: dict[str, object],
) -> str:
    """Backend 판정을 바꾸지 않는 세액감면 근거 검색어를 조립한다."""
    condition_text = ", ".join(
        f"{key}={value}" for key, value in conditions.items()
    )
    return (
        "청년창업 중소기업 세액감면 법령 근거와 적용 요건 "
        f"판정={'충족' if eligible else '미충족'} "
        f"사유={'; '.join(reasons)} 조건={condition_text}"
    )


async def _execute_graph(
    *,
    question: str,
    category: str | None,
    policy_id: int | None,
    top_k: int | None,
    decision: EligibilityDecision | None,
    user_context: dict | None,
    conversation_history: list[dict[str, str]],
    roadmap_step: RoadmapStep | None,
    user_id: int | None,
    notice_search: Callable[[GraphState], list[dict[str, object]]] | None,
    rag_runtime: RagRuntime,
    settings: Settings,
) -> GraphState:
    """두 HTTP 계약이 공유하는 단일 LangGraph 실행 함수."""
    normalized_question = validate_question(
        question,
        max_length=settings.max_question_length,
    )
    result_limit = validate_top_k(top_k or settings.default_top_k)
    resolved_user_context = user_context
    if resolved_user_context is None and user_id is not None:
        resolved_user_context = (
            get_database_user_profile(user_id, settings)
            if settings.vector_store_backend == "postgres"
            else get_mock_user_profile(user_id)
        )
    graph = rag_runtime.require_graph(settings, notice_search)
    return await graph.ainvoke(
        {
            "query": normalized_question,
            "category": category,
            "policy_id": policy_id,
            "top_k": result_limit,
            "decision": decision,
            "user_context": resolved_user_context,
            "conversation_history": conversation_history,
            "roadmap_step": roadmap_step,
        }
    )


def _backend_user_context(context: BackendUserContext | None) -> dict | None:
    """Backend camelCase Context를 기존 Graph UserProfile 계약으로 변환한다."""
    if context is None:
        return None
    return {
        "user_id": context.userId,
        "age": context.age,
        "region": context.region,
        "business": {
            "business_type": context.businessType,
            "industry": context.industry,
            "business_registered_at": context.businessRegisteredAt,
            "founded_at": context.foundedAt,
        },
    }


def _backend_source(source: dict[str, object]) -> RagChatSource:
    """Vector 또는 Notice metadata를 Backend answer_sources 계약으로 변환한다."""
    title = source.get("title") or source.get("name") or "근거 문서"
    url = (
        source.get("url")
        or source.get("sourceUrl")
        or source.get("source")
        or ""
    )
    excerpt = (
        source.get("excerpt")
        or source.get("content")
        or source.get("benefit")
        or ""
    )
    return RagChatSource(
        title=str(title),
        url=str(url),
        source=str(url),
        excerpt=str(excerpt)[:500],
    )


def _graph_guardrail_reason(
    answer_status: str,
) -> Literal[
    "out_of_scope",
    "insufficient_evidence",
    "generation_validation_failed",
] | None:
    """Graph 답변 상태를 Backend가 해석하는 Guardrail 사유로 변환한다."""
    if answer_status in {"no_result", "insufficient_evidence"}:
        return "insufficient_evidence"
    if answer_status == "error":
        return "generation_validation_failed"
    return None


def _to_domain_decision(
    decision: EligibilityDecisionRequest | None,
) -> EligibilityDecision | None:
    """API 판정 요청을 변경 불가능한 내부 판정 객체로 변환한다.

    Args:
        decision: Backend가 전달한 API 판정 객체 또는 None.

    Returns:
        reasons를 tuple로 고정한 내부 판정 객체 또는 None.
    """
    if decision is None:
        return None
    return EligibilityDecision(
        eligible=decision.eligible,
        reasons=tuple(decision.reasons),
    )


def _index_response(
    runtime: RagRuntime,
    response_status: Literal["ready", "already_ready"],
) -> IndexResponse:
    """현재 runtime 상태를 인덱스 API 응답으로 변환한다.

    Args:
        runtime: 문서·Chunk 수와 인덱스 생성 출처를 보관하는 runtime.
        response_status: 신규 준비 또는 기존 준비 상태를 나타내는 값.

    Returns:
        JSON 직렬화 가능한 IndexResponse 객체.
    """
    return IndexResponse(
        status=response_status,
        source=runtime.index_source or "embedding",
        document_count=runtime.document_count,
        chunk_count=runtime.chunk_count,
    )


@router.post("/recommendations", response_model=PolicyRecommendationResponse)
async def recommend_policies(
    request_body: PolicyRecommendationRequest,
    rag_runtime: RagRuntime = Depends(get_runtime),
    settings_config: Settings = Depends(get_settings),
) -> PolicyRecommendationResponse:
    """Mock 사용자 프로필과 질문을 이용해 전체 정책을 검색·요약한다.

    Args:
        request_body: 사용자 ID, 질문과 검색할 최대 Chunk 수.
        rag_runtime: 준비된 Vector Search와 LLM 팩토리를 제공하는 runtime.
        settings_config: 검색·Guardrail·LangSmith 설정.

    Returns:
        사용자 ID, 관련 정책별 출처, 요약과 Guardrail 사유.

    Raises:
        HTTPException: 사용자·인덱스가 없거나 입력 또는 외부 모델 호출 실패 시.
    """
    try:
        vector_search = rag_runtime.require_index()
        user_profile = (
            get_database_user_profile(request_body.user_id, settings_config)
            if settings_config.vector_store_backend == "postgres"
            else get_mock_user_profile(request_body.user_id)
        )
        discovery_service = PolicyDiscoveryService(
            vector_search=vector_search,
            llm_factory=rag_runtime.llm_factory,
            settings=settings_config,
        )
        discovery_answer = await discovery_service.discover(
            request_body.question,
            user=user_profile,
            top_k=request_body.top_k,
        )
        return PolicyRecommendationResponse(
            user_id=discovery_answer.user_id,
            answer=discovery_answer.answer,
            grounded=discovery_answer.grounded,
            policies=[
                MatchedPolicyResponse(
                    policy_id=matched_policy.policy_id,
                    title=matched_policy.title,
                    sources=[
                        _to_source_response(source)
                        for source in matched_policy.sources
                    ],
                )
                for matched_policy in discovery_answer.policies
            ],
            guardrail_reason=discovery_answer.guardrail_reason,
        )
    except RagIndexNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (MockDataNotFoundError, DatabaseDataNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except (ModelConfigurationError, LangSmithConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except RagInputError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise upstream_http_exception(
            exc,
            fallback_message="Policy recommendation generation failed.",
        ) from exc


def _to_source_response(source: SourceCitation) -> SourceResponse:
    """내부 출처 객체를 FastAPI 응답 schema로 변환한다.

    Args:
        source: RAG 서비스가 생성한 Chunk 출처 객체.

    Returns:
        API JSON 직렬화에 사용할 SourceResponse 객체.
    """
    return SourceResponse(
        chunk_id=source.chunk_id,
        policy_id=source.policy_id,
        title=source.title,
        source=source.source,
        page=source.page,
        excerpt=source.excerpt,
        score=source.score,
    )


def _graph_source_response(source: dict[str, object]) -> SourceResponse:
    """Graph가 선택한 실제 Vector 문서를 기존 API 출처 schema로 변환한다."""
    content = " ".join(str(source["content"]).split())[:500]
    return SourceResponse(
        chunk_id=str(source["chunk_id"]),
        policy_id=(
            int(source["policy_id"])
            if source.get("policy_id") is not None
            else None
        ),
        title=str(source["title"]),
        source=str(source["source"]),
        page=int(source["page"]),
        excerpt=content,
        score=float(source["score"]),
    )
