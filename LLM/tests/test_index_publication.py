"""A replacement index must not block or discard the working runtime."""
import asyncio
from threading import Event
from types import SimpleNamespace

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from src.core.config import Settings
from src.core.database import DatabaseConfigurationError
from src.serving import rag_routes
from src.serving.errors import ApiError
from src.serving.schemas import RagReindexRequest
from src.vectorstores.postgres import PostgresVectorSearch


SOURCE = {
    "document_id": "policy-1", "policy_id": 1, "source_id": 1,
    "source_type": "policy", "title": "청년창업 지원", "source": "db://policies/1",
    "content": "청년창업 지원 사업 안내",
}


def dense_search():
    dense = object.__new__(PostgresVectorSearch)
    dense.search = lambda *_args, **_kwargs: []
    return dense


@pytest.fixture
def prepared_runtime(monkeypatch):
    settings = Settings(_env_file=None, vector_store_backend="postgres", retrieval_mode="dense")
    runtime = rag_routes.RagRuntime(
        embedding_factory=lambda: DeterministicFakeEmbedding(size=32),
    )
    runtime.set_index(dense_search(), document_count=1, chunk_count=1, index_source="cache")
    monkeypatch.setattr(rag_routes, "load_elasticsearch_source_documents", lambda _settings: [SOURCE])
    hybrid = runtime.require_hybrid_index(settings)
    monkeypatch.setattr(
        rag_routes, "load_or_build_postgres_index",
        lambda **_kwargs: SimpleNamespace(
            vector_search=dense_search(), document_count=2, chunk_count=2,
            loaded_from_cache=True,
        ),
    )
    return runtime, settings, hybrid


@pytest.mark.parametrize("phase", ["_runtime_search", "load_elasticsearch_source_documents"])
def test_queries_keep_old_state_while_new_bm25_is_built(monkeypatch, prepared_runtime, phase):
    runtime, settings, old_hybrid = prepared_runtime
    old_graph = object()
    runtime._graph = old_graph
    runtime._graph_settings = settings

    async def exercise():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        finish = Event()

        build = getattr(rag_routes, phase)

        def blocked_build(*args):
            loop.call_soon_threadsafe(started.set)
            if not finish.wait(5):
                raise RuntimeError("test index build timed out")
            return build(*args)

        monkeypatch.setattr(rag_routes, phase, blocked_build)
        task = asyncio.create_task(
            rag_routes.adapter_reindex(RagReindexRequest(documentIds=[]), runtime, settings)
        )
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert await asyncio.wait_for(asyncio.to_thread(lambda: runtime.ready), 1)
            assert await asyncio.wait_for(
                asyncio.to_thread(runtime.require_hybrid_index, settings), 1
            ) is old_hybrid
            assert await asyncio.wait_for(
                asyncio.to_thread(runtime.require_graph, settings, None), 1
            ) is old_graph
            assert old_hybrid.bm25_search.search("청년창업", top_k=1)
            assert runtime.document_count == 1
        finally:
            finish.set()
        await task
        assert runtime.ready
        assert runtime.require_hybrid_index(settings) is not old_hybrid
        assert runtime.document_count == 2
        assert runtime._graph is None
        assert old_hybrid.bm25_search.search("청년창업", top_k=1)

    asyncio.run(exercise())


def test_initial_build_failure_stays_not_ready(monkeypatch, prepared_runtime):
    _runtime, settings, _hybrid = prepared_runtime
    empty = rag_routes.RagRuntime(embedding_factory=lambda: DeterministicFakeEmbedding(size=32))

    def fail(_settings):
        raise DatabaseConfigurationError("source unavailable")

    monkeypatch.setattr(rag_routes, "load_elasticsearch_source_documents", fail)
    with pytest.raises(ApiError) as error:
        asyncio.run(rag_routes.adapter_reindex(RagReindexRequest(documentIds=[]), empty, settings))
    assert error.value.status_code == 503
    assert not empty.ready
    with pytest.raises(rag_routes.RagIndexNotReadyError):
        empty.require_index()
