import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from src.core.config import Settings, get_settings
from src.data import get_document_catalog
from src.rag.backend_tasks import (
    AnnouncementSummaryGeneration,
    DeductibilityGeneration,
    LegalBasisGeneration,
    ReceiptExtractionGeneration,
)
from src.serving.app import create_app
from src.serving import rag_routes
from src.serving.rag_routes import RagRuntime
from src.rag.graph import ContextualizedQuestion, RouteDecision
from src.rag.answer import UnifiedAnswerResult
from src.rag.roadmap import (
    ROADMAP_MAX_COMPLETION_TOKENS,
    ROADMAP_REASONING_EFFORT,
    RoadmapCoachResult,
)
from src.rag.tax import TaxIntentDecision
from src.vectorstores.hybrid import HybridSearch
from tests.fakes import FakeStructuredChatModel, make_default_fake_model


def build_client(
    cache_path: Path,
    *,
    embedding_factory: Callable = lambda: DeterministicFakeEmbedding(size=32),
    llm_factory: Callable = make_default_fake_model,
    retrieval_mode: str = "dense",
    vector_store_backend: str = "in_memory",
) -> TestClient:
    runtime = RagRuntime(
        embedding_factory=embedding_factory,
        llm_factory=llm_factory,
    )
    app = create_app(runtime=runtime)
    settings = Settings(
        _env_file=None,
        langsmith_tracing=False,
        vector_store_backend=vector_store_backend,
        retrieval_mode=retrieval_mode,
        min_relevance_score=0.0,
        chunk_size=500,
        chunk_overlap=50,
        embedding_model="test-embedding-model",
        vector_index_cache_path=cache_path,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def add_test_tax_evidence(client: TestClient) -> None:
    """Backend 전용 Tax API 테스트에 사용할 법령 Chunk를 추가한다."""
    client.app.state.rag_runtime.require_index().add_chunks(
        [
            {
                "chunk_id": "tax-api-1",
                "policy_id": None,
                "title": "조세특례제한법 및 소득세법 안내",
                "source": "db://tax_documents/1",
                "page": 1,
                "content": (
                    "청년창업 중소기업 세액감면 적용 요건과 사업 관련 지출의 "
                    "필요경비 인정에는 법령 요건, 업무 관련성 및 적격 증빙 확인이 필요하다."
                ),
                "source_type": "tax_document",
                "source_id": 1,
            }
        ]
    )


def test_index_uses_hybrid_search_when_configured(tmp_path: Path) -> None:
    client = build_client(
        tmp_path / "index.json",
        retrieval_mode="hybrid",
    )

    response = client.post("/internal/rag/index")

    assert response.status_code == 200
    assert isinstance(client.app.state.rag_runtime.require_index(), HybridSearch)


def test_tax_evidence_search_uses_tax_filter_and_exact_legal_match(monkeypatch) -> None:
    rrf_document = {
        "chunk_id": "rrf-tax-1",
        "policy_id": None,
        "title": "조세특례제한법 제6조 일반 검색",
        "source": "db://tax_documents/1",
        "page": 1,
        "content": "일반 검색 근거",
        "source_type": "tax_document",
        "source_id": 1,
        "score": 0.8,
    }
    exact_document = {
        "chunk_id": "exact-tax-1",
        "policy_id": None,
        "title": "조세특례제한법 제6조",
        "source": "db://tax_documents/2",
        "page": 1,
        "content": "정확 조문 근거",
        "source_type": "tax_document",
        "source_id": 2,
        "score": 1.0,
    }

    class TrackingHybridSearch(HybridSearch):
        def __init__(self) -> None:
            self.source_types = None
            self.exact_reference = None

        def search_stages(self, _query: str, **kwargs):
            self.source_types = kwargs.get("source_types")
            return [], [], [rrf_document]

        def search_legal_reference(self, law_name: str, article: str, **_kwargs):
            self.exact_reference = (law_name, article)
            return [exact_document]

    search = TrackingHybridSearch()
    runtime = RagRuntime()
    runtime.set_index(
        search,
        document_count=2,
        chunk_count=2,
        index_source="cache",
    )
    monkeypatch.setattr(
        rag_routes,
        "rerank_documents",
        lambda _query, documents, **_kwargs: documents,
    )

    evidence = asyncio.run(
        rag_routes._retrieve_tax_evidence(
            "조세특례제한법 제6조",
            rag_runtime=runtime,
            settings=Settings(_env_file=None, min_relevance_score=0.0),
        )
    )

    assert search.source_types == ("tax_document",)
    assert search.exact_reference == ("조세특례제한법", "6")
    assert [document["chunk_id"] for document in evidence] == [
        "exact-tax-1",
        "rrf-tax-1",
    ]


def test_backend_adapter_ready_and_reindex_paths(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")

    before = client.get("/rag/ready")
    indexed = client.post("/rag/reindex", json={"documentIds": []})
    after = client.get("/rag/ready")

    assert before.status_code == 200
    assert before.json()["index_ready"] is False
    assert indexed.status_code == 200
    assert indexed.json()["status"] == "ready"
    assert after.json()["index_ready"] is True


def test_backend_explicit_reindex_checks_sources_even_when_runtime_is_ready(
    tmp_path: Path,
) -> None:
    embedding_calls = 0

    def embedding_factory() -> DeterministicFakeEmbedding:
        nonlocal embedding_calls
        embedding_calls += 1
        return DeterministicFakeEmbedding(size=32)

    client = build_client(
        tmp_path / "index.json",
        embedding_factory=embedding_factory,
    )

    first = client.post("/rag/reindex", json={})
    second = client.post("/rag/reindex", json={})

    assert first.json()["status"] == "ready"
    assert second.json()["status"] == "already_ready"
    assert embedding_calls == 2
    assert second.json()["requested_document_ids"] == []


def test_backend_partial_reindex_uses_postgres_document_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    received: dict[str, object] = {}

    class FakePostgresVectorSearch:
        def __init__(self, *, embedding, settings) -> None:
            received["embedding"] = embedding
            received["settings"] = settings
            self.last_embedded_count = 2

        def reindex_document_ids(
            self,
            document_ids: list[int],
            *,
            force: bool,
        ) -> list[int]:
            received["document_ids"] = document_ids
            received["force"] = force
            return document_ids

        def counts(self) -> tuple[int, int]:
            return 12, 34

        def search(self, *_args, **_kwargs):
            return []

        def add_chunks(self, _chunks):
            return []

        def get_chunks(self):
            return []

    monkeypatch.setattr(
        rag_routes,
        "PostgresVectorSearch",
        FakePostgresVectorSearch,
    )
    client = build_client(
        tmp_path / "index.json",
        vector_store_backend="postgres",
    )

    response = client.post(
        "/rag/reindex",
        json={"documentIds": [9, 7, 9], "force": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "source": "embedding",
        "document_count": 2,
        "chunk_count": 2,
        "requested_document_ids": [9, 7],
    }
    assert received["document_ids"] == [9, 7]
    assert received["force"] is True
    assert client.app.state.rag_runtime.document_count == 12
    assert client.app.state.rag_runtime.chunk_count == 34


def test_backend_partial_reindex_rejects_in_memory_backend(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/rag/reindex",
        json={"documentIds": [1]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_backend_adapter_policy_chat_returns_backend_source_contract(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel(
        {
            RouteDecision: {"route": "policy", "personalized": True},
            UnifiedAnswerResult: {
                "answer": "사용자 조건에 맞는 정책 근거입니다.",
                "status": "success",
                "cited_source_numbers": [1],
            },
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
        retrieval_mode="hybrid",
    )
    client.post("/rag/reindex", json={})

    response = client.post(
        "/rag/chat",
        json={
            "category": "policy",
            "question": "예비창업 지원 정책 알려줘",
            "userContext": {
                "userId": 1,
                "age": 29,
                "region": "서울",
                "businessType": "간이과세자",
                "industry": "소프트웨어",
                "foundedAt": "2024-03-01",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "policy"
    assert body["status"] == "success"
    assert body["grounded"] is True
    assert body["guardrail_reason"] is None
    assert body["sources"]
    assert body["sources"][0]["url"] == body["sources"][0]["source"]
    assert "서울" in model.last_prompt_text
    assert "소프트웨어" in model.last_prompt_text


def test_backend_adapter_passes_conversation_history_to_graph(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel(
        {
            ContextualizedQuestion: {
                "standalone_question": "세액 계산에서 가족이 두 명일 때 원천징수세액은?",
            },
            RouteDecision: {"route": "tax", "personalized": False},
            TaxIntentDecision: {
                "calculation_required": False,
                "calculation_type": None,
                "reason": "세법 설명 질문",
            },
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/rag/chat",
        json={
            "category": "tax",
            "question": "가족이 두 명이면?",
            "conversationHistory": [
                {"role": "user", "content": "원천징수 세액 계산 방법 알려줘"},
                {"role": "assistant", "content": "가족 수를 알려주세요."},
            ],
        },
    )

    assert response.status_code == 200
    assert "가족이 두 명일 때 원천징수세액" in model.last_prompt_text


def test_backend_adapter_roadmap_uses_dedicated_single_call_branch(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel(
        {
            RoadmapCoachResult: {
                "in_scope": True,
                "redirect": "none",
                "answer": "현재 단계에서는 PSST 초안과 마감 일정을 먼저 정리하세요.",
            }
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/rag/chat",
        json={
            "category": "roadmap",
            "question": "그다음에는 무엇을 준비할까요?",
            "roadmapStep": "C",
            "userContext": {
                "userId": 1,
                "age": 28,
                "region": "서울",
                "businessType": "개인사업자",
                "industry": "소프트웨어",
                "foundedAt": "2024-01-10",
            },
            "conversationHistory": [
                {"role": "user", "content": "지원사업을 찾아봤어요."},
                {"role": "assistant", "content": "후보 공고를 정리해 보세요."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "현재 단계에서는 PSST 초안과 마감 일정을 먼저 정리하세요.",
        "sources": [],
        "grounded": False,
        "route": "roadmap",
        "status": "success",
        "guardrail_reason": None,
    }
    assert model.call_count == 1
    assert (
        model.bound_kwargs["max_completion_tokens"]
        == ROADMAP_MAX_COMPLETION_TOKENS
    )
    assert model.bound_kwargs["reasoning_effort"] == ROADMAP_REASONING_EFFORT
    assert "현재 단계: C" in model.last_prompt_text
    assert "지원사업을 찾아봤어요" in model.last_prompt_text


def test_backend_adapter_notice_uses_only_supplied_results(tmp_path: Path) -> None:
    model = FakeStructuredChatModel(
        {
            RouteDecision: {"route": "notice", "personalized": False},
            UnifiedAnswerResult: {
                "answer": "현재 신청 가능한 공고입니다.",
                "status": "success",
                "cited_source_numbers": [1],
            },
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/rag/chat",
        json={
            "category": "policy",
            "question": "서울에서 지금 신청 가능한 사업 있어?",
            "noticeResults": [
                {
                    "announcementId": 7,
                    "title": "서울 청년창업 공고",
                    "sourceUrl": "https://example.com/notices/7",
                    "benefit": "사업화 지원",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "notice"
    assert body["sources"] == [
        {
            "title": "서울 청년창업 공고",
            "url": "https://example.com/notices/7",
            "source": "https://example.com/notices/7",
            "excerpt": "사업화 지원",
        }
    ]


def test_backend_adapter_missing_notice_payload_is_unavailable(
    tmp_path: Path,
) -> None:
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: FakeStructuredChatModel(
            {RouteDecision: {"route": "notice", "personalized": False}}
        ),
    )

    response = client.post(
        "/rag/chat",
        json={
            "category": "policy",
            "question": "지금 신청 가능한 사업 있어?",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "integration_unavailable"
    assert response.json()["guardrail_reason"] is None


def test_backend_chat_returns_out_of_scope_guardrail_without_model_call(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel({})
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/rag/chat",
        json={"category": "policy", "question": "오늘 날씨 알려줘"},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "policy"
    assert response.json()["status"] == "no_result"
    assert response.json()["guardrail_reason"] == "out_of_scope"
    assert model.call_count == 0


def test_backend_adapter_empty_notice_payload_means_no_result(
    tmp_path: Path,
) -> None:
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: FakeStructuredChatModel(
            {RouteDecision: {"route": "notice", "personalized": False}}
        ),
    )

    response = client.post(
        "/rag/chat",
        json={
            "category": "policy",
            "question": "지금 신청 가능한 사업 있어?",
            "noticeResults": [],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_result"
    assert response.json()["guardrail_reason"] == "insufficient_evidence"


def test_backend_adapter_rejects_notice_without_contract_id(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/rag/chat",
        json={
            "category": "policy",
            "question": "지금 신청 가능한 사업 있어?",
            "noticeResults": [{"id": 7, "title": "잘못된 계약"}],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["retryable"] is False


def test_backend_legal_basis_preserves_decision_and_returns_sources(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel(
        {
            LegalBasisGeneration: {
                "legal_basis": "검색된 법령에 따른 세액감면 근거입니다.",
                "cited_source_numbers": [1],
            }
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
        retrieval_mode="hybrid",
    )
    client.post("/rag/reindex", json={})
    add_test_tax_evidence(client)

    response = client.post(
        "/rag/legal-basis",
        json={
            "eligible": True,
            "reasons": ["나이 요건 충족", "창업 후 5년 이내"],
            "conditions": {
                "age": 29,
                "region": "서울",
                "industry": "소프트웨어",
                "foundedAt": "2026-01-15",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reasons"] == ["나이 요건 충족", "창업 후 5년 이내"]
    assert body["legalBasis"] == "검색된 법령에 따른 세액감면 근거입니다."
    assert body["grounded"] is True
    assert body["status"] == "success"
    assert body["llmUsed"] is True
    assert body["sources"]


def test_backend_legal_basis_requires_ready_index(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/rag/legal-basis",
        json={"eligible": False, "reasons": ["나이 요건 미충족"]},
    )

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "RAG_INDEX_NOT_READY",
        "message": "RAG index is not ready. Call POST /internal/rag/index first.",
        "retryable": True,
    }


def test_backend_deductibility_returns_structured_grounded_result(
    tmp_path: Path,
) -> None:
    model = FakeStructuredChatModel(
        {
            DeductibilityGeneration: {
                "deductible": True,
                "confidence": 0.82,
                "basis": "업무 관련성과 적격 증빙을 확인해야 합니다.",
                "cited_source_numbers": [1],
            }
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
        retrieval_mode="hybrid",
    )
    client.post("/rag/reindex", json={})
    add_test_tax_evidence(client)

    response = client.post(
        "/rag/deductibility",
        json={
            "category": "사무용품",
            "amount": 18000,
            "vendor": "예시상점",
            "items": ["노트", "펜"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deductible"] is True
    assert body["confidence"] == 0.82
    assert body["grounded"] is True
    assert body["status"] == "success"
    assert body["llmUsed"] is True
    assert body["sources"]


def test_backend_announcement_summary_preserves_source(tmp_path: Path) -> None:
    model = FakeStructuredChatModel(
        {
            AnnouncementSummaryGeneration: {
                "target": "만 39세 이하 예비창업자",
                "benefit": "사업화 자금 지원",
                "period": "2026-09-01 ~ 2026-09-30",
                "documents": "사업계획서",
                "notes": "온라인 신청",
            }
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/rag/summarize-announcement",
        json={
            "rawContent": "만 39세 이하 예비창업자에게 사업화 자금을 지원합니다.",
            "source": "https://example.com/notices/7",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "target": "만 39세 이하 예비창업자",
        "benefit": "사업화 자금 지원",
        "period": "2026-09-01 ~ 2026-09-30",
        "documents": "사업계획서",
        "notes": "온라인 신청",
        "source": "https://example.com/notices/7",
        "llmUsed": True,
    }


def test_backend_model_timeout_uses_common_retryable_error(
    tmp_path: Path,
) -> None:
    def timeout_factory() -> FakeStructuredChatModel:
        raise TimeoutError("sensitive timeout detail")

    client = build_client(
        tmp_path / "index.json",
        llm_factory=timeout_factory,
    )

    response = client.post(
        "/rag/summarize-announcement",
        json={"rawContent": "공고문 원문"},
    )

    assert response.status_code == 504
    assert response.json()["error"] == {
        "code": "UPSTREAM_TIMEOUT",
        "message": "The upstream model request timed out.",
        "retryable": True,
    }
    assert "sensitive" not in response.text


def test_backend_invalid_summary_uses_common_validation_error(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/rag/summarize-announcement",
        json={"rawContent": "   "},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["retryable"] is False


def test_backend_receipt_ocr_accepts_multipart_image(tmp_path: Path) -> None:
    model = FakeStructuredChatModel(
        {
            ReceiptExtractionGeneration: {
                "date": "2026-09-09",
                "vendor": "예시상점",
                "amount": 18000,
                "items": ["노트", "펜"],
                "category": "사무용품",
            }
        }
    )
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: model,
    )

    response = client.post(
        "/ocr/receipt",
        files={"image": ("receipt.jpg", b"fake-jpeg", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-09-09",
        "vendor": "예시상점",
        "amount": 18000,
        "items": ["노트", "펜"],
        "category": "사무용품",
        "source": "vision",
        "llmUsed": True,
    }


def test_backend_receipt_ocr_rejects_unsupported_media_type(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/ocr/receipt",
        files={"image": ("receipt.txt", b"not-an-image", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["error"] == {
        "code": "UNSUPPORTED_MEDIA_TYPE",
        "message": "receipt image must be JPEG, PNG, or WebP",
        "retryable": False,
    }


def test_policy_answer_without_index_reports_integration_unavailable(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path / "index.json")

    response = client.post(
        "/internal/rag/answer",
        json={"question": "지원 대상은 누구야?", "policy_id": 101},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "policy"
    assert response.json()["status"] == "integration_unavailable"


def test_notice_answer_does_not_require_rag_index(tmp_path: Path) -> None:
    client = build_client(
        tmp_path / "index.json",
        llm_factory=lambda: FakeStructuredChatModel(
            {RouteDecision: {"route": "notice", "personalized": False}}
        ),
    )

    response = client.post(
        "/internal/rag/answer",
        json={"question": "지금 신청 가능한 창업 지원사업 있어?"},
    )

    assert response.status_code == 200
    assert response.json()["route"] == "notice"
    assert response.json()["status"] == "integration_unavailable"
    assert response.json()["sources"] == []


def test_index_ready_and_answer_flow_with_fake_models(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")

    index_response = client.post("/internal/rag/index")
    duplicate_response = client.post("/internal/rag/index")
    ready_response = client.get("/internal/rag/ready")
    answer_response = client.post(
        "/internal/rag/answer",
        json={
            "question": "초기창업 지원사업의 지원 대상은 누구야?",
            "policy_id": 101,
            "top_k": 2,
            "decision": {
                "eligible": True,
                "reasons": ["연령 조건 충족", "지역 조건 충족"],
            },
        },
    )

    assert index_response.status_code == 200
    index_body = index_response.json()
    assert index_body["status"] == "ready"
    assert index_body["source"] == "embedding"
    assert index_body["document_count"] == len(get_document_catalog())
    assert index_body["chunk_count"] > 0
    assert duplicate_response.json()["status"] == "already_ready"
    assert ready_response.json()["index_ready"] is True
    assert answer_response.status_code == 200
    body = answer_response.json()
    assert body["grounded"] is True
    assert body["route"] == "policy"
    assert body["status"] == "success"
    assert body["sources"]
    assert all(source["policy_id"] == 101 for source in body["sources"])
    assert body["decision"] == {
        "eligible": True,
        "reasons": ["연령 조건 충족", "지역 조건 충족"],
    }


def test_new_server_runtime_loads_local_cache_without_reindexing(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "index.json"
    first_client = build_client(cache_path)
    assert first_client.post("/internal/rag/index").json()["source"] == "embedding"

    restarted_client = build_client(cache_path)
    response = restarted_client.post("/internal/rag/index")

    assert response.status_code == 200
    assert response.json()["source"] == "cache"


def test_health_does_not_create_embedding_or_llm(tmp_path: Path) -> None:
    calls = {"embedding": 0, "llm": 0}

    def embedding_factory() -> DeterministicFakeEmbedding:
        calls["embedding"] += 1
        return DeterministicFakeEmbedding(size=16)

    def llm_factory() -> FakeListChatModel:
        calls["llm"] += 1
        return FakeListChatModel(responses=["호출되면 안 됨"])

    client = build_client(
        tmp_path / "index.json",
        embedding_factory=embedding_factory,
        llm_factory=llm_factory,
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert calls == {"embedding": 0, "llm": 0}


def test_personalized_policy_recommendation_uses_user_id_not_policy_input(
    tmp_path: Path,
) -> None:
    client = build_client(tmp_path / "index.json")
    client.post("/internal/rag/index")

    response = client.post(
        "/internal/rag/recommendations",
        json={
            "user_id": 1,
            "question": "내 조건과 관련된 지원정책을 알려줘",
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == 1
    assert body["grounded"] is True
    assert body["policies"]
    assert all(policy["sources"] for policy in body["policies"])


def test_unknown_mock_user_returns_not_found(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")
    client.post("/internal/rag/index")

    response = client.post(
        "/internal/rag/recommendations",
        json={"user_id": 999, "question": "관련 정책을 알려줘"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert "Mock user not found" in response.json()["error"]["message"]


def test_internal_answer_accepts_explicit_evaluation_user_context(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")
    client.post("/internal/rag/index")

    response = client.post("/internal/rag/answer", json={
        "user_id": 4,
        "user_context": {"userId": 4, "age": None, "region": None},
        "question": "오늘 날씨가 어때?",
    })

    assert response.status_code == 200
    assert response.json()["guardrail_reason"] == "out_of_scope"


def test_unrelated_question_returns_guardrail_answer(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")
    client.post("/internal/rag/index")

    response = client.post(
        "/internal/rag/recommendations",
        json={"user_id": 1, "question": "오늘 날씨가 어때?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "user_id": 1,
        "answer": "그 질문에는 답변할 수 없습니다",
        "grounded": False,
        "policies": [],
        "guardrail_reason": "out_of_scope",
    }


def test_mixed_domain_question_returns_guardrail_answer(tmp_path: Path) -> None:
    client = build_client(tmp_path / "index.json")
    client.post("/internal/rag/index")

    response = client.post(
        "/internal/rag/recommendations",
        json={
            "user_id": 1,
            "question": "나와 관련된 정책 알려줘 그리고 파이썬 append에 관해 알려줘",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "그 질문에는 답변할 수 없습니다"
    assert response.json()["policies"] == []
    assert response.json()["guardrail_reason"] == "out_of_scope"
