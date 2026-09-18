from pathlib import Path

from langchain_core.embeddings import Embeddings

from src.core.config import Settings
from src.data import get_document_catalog
from src.features.indexing import load_or_build_document_index


class CountingEmbedding(Embeddings):
    def __init__(self) -> None:
        self.document_calls = 0
        self.query_calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        length = float(len(text))
        checksum = float(sum(ord(character) for character in text) % 997)
        return [length or 1.0, checksum or 1.0, 1.0]


def make_settings(cache_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "embedding_model": "test-embedding-model",
        "chunk_size": 500,
        "chunk_overlap": 50,
        "vector_index_cache_path": cache_path,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_second_build_loads_cache_without_document_embedding(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    settings = make_settings(cache_path)
    first_embedding = CountingEmbedding()

    first = load_or_build_document_index(
        embedding=first_embedding,
        settings=settings,
        catalog=get_document_catalog(),
    )

    second_embedding = CountingEmbedding()
    second = load_or_build_document_index(
        embedding=second_embedding,
        settings=settings,
        catalog=get_document_catalog(),
    )

    assert first.loaded_from_cache is False
    assert first_embedding.document_calls == 1
    assert cache_path.is_file()
    assert cache_path.with_suffix(".manifest.json").is_file()
    assert second.loaded_from_cache is True
    assert second_embedding.document_calls == 0
    assert second.chunk_count == first.chunk_count


def test_loaded_cache_can_search_with_only_query_embedding(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    settings = make_settings(cache_path)
    load_or_build_document_index(
        embedding=CountingEmbedding(),
        settings=settings,
        catalog=get_document_catalog(),
    )
    search_embedding = CountingEmbedding()

    cached = load_or_build_document_index(
        embedding=search_embedding,
        settings=settings,
        catalog=get_document_catalog(),
    )
    results = cached.vector_search.search("지원 정책", top_k=2)

    assert search_embedding.document_calls == 0
    assert search_embedding.query_calls == 1
    assert len(results) == 2


def test_changed_chunk_settings_invalidate_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    catalog = get_document_catalog()
    load_or_build_document_index(
        embedding=CountingEmbedding(),
        settings=make_settings(cache_path),
        catalog=catalog,
    )
    changed_embedding = CountingEmbedding()

    rebuilt = load_or_build_document_index(
        embedding=changed_embedding,
        settings=make_settings(cache_path, chunk_size=400),
        catalog=catalog,
    )

    assert rebuilt.loaded_from_cache is False
    assert changed_embedding.document_calls == 1


def test_changed_embedding_model_invalidates_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    catalog = get_document_catalog()
    load_or_build_document_index(
        embedding=CountingEmbedding(),
        settings=make_settings(cache_path),
        catalog=catalog,
    )
    changed_embedding = CountingEmbedding()

    rebuilt = load_or_build_document_index(
        embedding=changed_embedding,
        settings=make_settings(cache_path, embedding_model="new-model"),
        catalog=catalog,
    )

    assert rebuilt.loaded_from_cache is False
    assert changed_embedding.document_calls == 1


def test_force_rebuild_ignores_valid_cache(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    settings = make_settings(cache_path)
    catalog = get_document_catalog()
    load_or_build_document_index(
        embedding=CountingEmbedding(),
        settings=settings,
        catalog=catalog,
    )
    forced_embedding = CountingEmbedding()

    rebuilt = load_or_build_document_index(
        embedding=forced_embedding,
        settings=settings,
        catalog=catalog,
        force=True,
    )

    assert rebuilt.loaded_from_cache is False
    assert forced_embedding.document_calls == 1


def test_corrupted_cache_is_rebuilt_safely(tmp_path: Path) -> None:
    cache_path = tmp_path / "rag-index.json"
    settings = make_settings(cache_path)
    catalog = get_document_catalog()
    load_or_build_document_index(
        embedding=CountingEmbedding(),
        settings=settings,
        catalog=catalog,
    )
    cache_path.write_text("not valid json", encoding="utf-8")
    replacement_embedding = CountingEmbedding()

    rebuilt = load_or_build_document_index(
        embedding=replacement_embedding,
        settings=settings,
        catalog=catalog,
    )

    assert rebuilt.loaded_from_cache is False
    assert replacement_embedding.document_calls == 1
