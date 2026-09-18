from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from src.core.config import Settings
from src.data.contracts import VectorSearchResult
from src.rag.reranker import CohereRerankError, rerank_documents


DOCUMENTS: list[VectorSearchResult] = [
    {
        "chunk_id": "policy-1-chunk-1",
        "policy_id": 1,
        "title": "정책 1",
        "source": "db://policies/1",
        "page": 1,
        "content": "첫 번째 정책 내용",
        "score": 0.8,
    },
    {
        "chunk_id": "policy-2-chunk-1",
        "policy_id": 2,
        "title": "정책 2",
        "source": "db://policies/2",
        "page": 1,
        "content": "두 번째 정책 내용",
        "score": 0.7,
    },
]


def test_cohere_rerank_preserves_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    received: dict[str, object] = {}

    class FakeClient:
        def __init__(self, api_key: str) -> None:
            received["api_key"] = api_key

        def rerank(self, **kwargs: object) -> SimpleNamespace:
            received.update(kwargs)
            return SimpleNamespace(
                results=[SimpleNamespace(index=1, relevance_score=0.95)]
            )

    monkeypatch.setattr("src.rag.reranker.cohere.ClientV2", FakeClient)
    settings = Settings(
        _env_file=None,
        cohere_api_key=SecretStr("test-key"),
        cohere_rerank_model="rerank-v4.0-fast",
    )

    results = rerank_documents("청년 정책", DOCUMENTS, top_n=1, settings=settings)

    assert results == [{**DOCUMENTS[1], "score": 0.95}]
    assert received["model"] == "rerank-v4.0-fast"
    assert received["documents"] == [document["content"] for document in DOCUMENTS]


def test_cohere_rerank_requires_configuration() -> None:
    with pytest.raises(CohereRerankError, match="COHERE_API_KEY"):
        rerank_documents(
            "청년 정책",
            DOCUMENTS,
            top_n=1,
            settings=Settings(_env_file=None, cohere_api_key=None),
        )
