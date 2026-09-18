import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from langchain_core.embeddings import Embeddings

from src.core.config import Settings, get_settings
from src.data import get_document_catalog, get_rag_chunks
from src.data.contracts import DocumentCatalogEntry, RagChunk, RagSourceDocument
from src.data.document_catalog import SOURCE_PDF_DIR
from src.data.postgres_repository import get_rag_source_documents
from src.features.document_processing import load_pdf_pages, split_pdf_pages, split_text
from src.models import get_embedding_model
from src.vectorstores.base import VectorSearch
from src.vectorstores.in_memory import InMemoryVectorSearch
from src.vectorstores.postgres import PostgresVectorSearch


INDEX_CACHE_VERSION = 1


@dataclass(frozen=True, slots=True)
class IndexManifest:
    """로컬 Vector 캐시의 유효성 검증에 필요한 상태 정보."""

    version: int
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    catalog: list[DocumentCatalogEntry]
    source_hashes: dict[str, str]


@dataclass(frozen=True, slots=True)
class CachedVectorIndex:
    """로드 또는 생성된 Vector 인덱스와 캐시 사용 결과."""

    vector_search: VectorSearch
    document_count: int
    chunk_count: int
    loaded_from_cache: bool


def build_mock_vector_index(
    embedding: Embeddings | None = None,
) -> VectorSearch:
    """Mock Chunk를 임베딩해 검색 가능한 메모리 인덱스를 생성한다.

    Args:
        embedding: 테스트에서 주입할 Embedding 구현체. None이면 환경설정에 지정된
            실제 OpenAI Embedding 모델을 사용한다.

    Returns:
        Mock Chunk가 적재된 VectorSearch 구현체.
    """
    return build_vector_index(get_rag_chunks(), embedding=embedding)


def prepare_document_chunks(
    *,
    catalog: list[DocumentCatalogEntry] | None = None,
    source_dir: Path = SOURCE_PDF_DIR,
    settings: Settings | None = None,
) -> list[RagChunk]:
    """catalog의 PDF를 불러와 metadata가 포함된 RAG Chunk로 변환한다.

    Args:
        catalog: 처리할 PDF와 정책 ID 목록. None이면 기본 catalog를 사용한다.
        source_dir: 원본 PDF가 위치한 읽기 전용 디렉터리.
        settings: Chunk 크기와 중첩 설정. None이면 환경설정을 사용한다.

    Returns:
        모든 PDF의 페이지를 분할한 RAG Chunk 목록.
    """
    settings_config = settings or get_settings()
    document_catalog = catalog if catalog is not None else get_document_catalog()

    rag_chunks: list[RagChunk] = []
    for document_entry in document_catalog:
        page_documents = load_pdf_pages(document_entry, source_dir=source_dir)
        rag_chunks.extend(
            split_pdf_pages(
                page_documents,
                chunk_size=settings_config.chunk_size,
                chunk_overlap=settings_config.chunk_overlap,
            )
        )
    return rag_chunks


def prepare_database_chunks(
    source_documents: list[RagSourceDocument],
    *,
    settings: Settings,
) -> list[RagChunk]:
    """실제 DB 정책·공고문을 metadata가 포함된 Chunk로 변환한다.

    Args:
        source_documents: PostgreSQL에서 읽은 정책·공고문 원천 문서.
        settings: Chunk 크기와 중첩 설정.

    Returns:
        pgvector에 적재할 정책 ID와 원천 ID가 포함된 Chunk 목록.
    """
    chunks: list[RagChunk] = []
    for source_document in source_documents:
        chunk_contents = split_text(
            source_document["content"],
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        for chunk_number, chunk_content in enumerate(chunk_contents, start=1):
            chunks.append(
                {
                    "chunk_id": (
                        f"{source_document['source_type']}-"
                        f"{source_document['source_id']}-chunk-{chunk_number}"
                    ),
                    "policy_id": source_document["policy_id"],
                    "title": source_document["title"],
                    "source": source_document["source"],
                    "page": 1,
                    "content": chunk_content,
                    "source_type": source_document["source_type"],
                    "source_id": source_document["source_id"],
                }
            )
    return chunks


def load_or_build_postgres_index(
    *,
    embedding: Embeddings,
    settings: Settings,
    force: bool = False,
) -> CachedVectorIndex:
    """실제 DB 원천 문서를 Chunking하고 pgvector 인덱스를 준비한다.

    Args:
        embedding: 신규·변경 Chunk와 Query에 사용할 Embedding 구현체.
        settings: PostgreSQL, 모델 및 Chunk 설정.
        force: True이면 기존 pgvector Chunk도 모두 다시 임베딩한다.

    Returns:
        pgvector 검색 구현체와 실제 문서·Chunk 수 및 재사용 여부.

    Notes:
        원본 정책·공고문은 읽기만 하고 변경된 파생 Chunk만 임베딩한다.
    """
    source_documents = get_rag_source_documents(settings)
    chunks = prepare_database_chunks(source_documents, settings=settings)
    vector_search = PostgresVectorSearch(embedding=embedding, settings=settings)
    vector_search.add_chunks(chunks, force=force)
    document_count, chunk_count = vector_search.counts()
    return CachedVectorIndex(
        vector_search=vector_search,
        document_count=document_count,
        chunk_count=chunk_count,
        loaded_from_cache=vector_search.last_embedded_count == 0,
    )


def build_document_vector_index(
    embedding: Embeddings | None = None,
    *,
    catalog: list[DocumentCatalogEntry] | None = None,
    source_dir: Path = SOURCE_PDF_DIR,
    settings: Settings | None = None,
) -> VectorSearch:
    """catalog PDF를 로드·분할·임베딩해 메모리 인덱스를 생성한다.

    Args:
        embedding: Chunk를 벡터화할 Embedding 구현체. None이면 실제 설정 모델.
        catalog: 처리할 문서 catalog. None이면 기본 catalog.
        source_dir: 원본 PDF가 위치한 읽기 전용 디렉터리.
        settings: Chunking에 사용할 설정. None이면 환경설정.

    Returns:
        실제 PDF Chunk가 적재된 VectorSearch 구현체.
    """
    rag_chunks = prepare_document_chunks(
        catalog=catalog,
        source_dir=source_dir,
        settings=settings,
    )
    return build_vector_index(rag_chunks, embedding=embedding)


def build_vector_index(
    chunks: list[RagChunk],
    *,
    embedding: Embeddings | None = None,
) -> VectorSearch:
    """RAG Chunk를 임베딩해 새로운 In-memory Vector 인덱스를 생성한다.

    Args:
        chunks: 임베딩하고 적재할 RAG Chunk 목록.
        embedding: 사용할 Embedding 구현체. None이면 환경설정의 실제 모델.

    Returns:
        Chunk가 적재되어 검색 가능한 VectorSearch 구현체.

    Raises:
        ValueError: 적재할 Chunk가 하나도 없을 때.

    Notes:
        `add_chunks()` 호출에서 문서 Embedding API 요청이 발생할 수 있다.
    """
    if not chunks:
        raise ValueError("At least one RAG chunk is required to build an index")
    embedding_model = embedding or get_embedding_model()
    vector_search = InMemoryVectorSearch(embedding=embedding_model)
    # 이 호출이 내부에서 embedding.embed_documents()를 실행한다.
    vector_search.add_chunks(chunks)
    return vector_search


def load_or_build_document_index(
    *,
    embedding: Embeddings,
    settings: Settings,
    catalog: list[DocumentCatalogEntry],
    source_dir: Path = SOURCE_PDF_DIR,
    force: bool = False,
) -> CachedVectorIndex:
    """유효한 로컬 인덱스를 로드하거나 문서를 한 번 임베딩해 저장한다.

    Args:
        embedding: 캐시 로드 또는 신규 문서 Embedding에 사용할 모델 구현체.
        settings: Embedding 모델명, Chunk 설정과 캐시 경로를 담은 설정.
        catalog: 인덱싱할 PDF와 정책 ID의 연결 정보.
        source_dir: 원본 PDF가 위치한 읽기 전용 디렉터리.
        force: True이면 유효한 캐시도 무시하고 문서를 다시 임베딩한다.

    Returns:
        검색 구현체, 문서·Chunk 수와 캐시 사용 여부를 담은 결과.

    Notes:
        원본 PDF hash, 모델명, Chunk 설정, catalog 중 하나라도 달라지면 캐시를
        무효화한다. 신규 인덱스의 `add_chunks()`에서만 문서 Embedding이 발생한다.
    """
    vector_cache_path = settings.resolved_vector_index_cache_path
    manifest_path = vector_cache_path.with_suffix(".manifest.json")
    embedding_model_name = settings.embedding_model.strip() or repr(embedding)
    current_source_hashes = _source_hashes(catalog, source_dir)

    if not force:
        stored_manifest = _read_manifest(manifest_path)
        if _cache_is_valid(
            stored_manifest,
            cache_path=vector_cache_path,
            embedding_model=embedding_model_name,
            settings=settings,
            catalog=catalog,
            source_hashes=current_source_hashes,
        ):
            try:
                cached_vector_search = InMemoryVectorSearch.load(
                    vector_cache_path,
                    embedding=embedding,
                )
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
            else:
                return CachedVectorIndex(
                    vector_search=cached_vector_search,
                    document_count=len(catalog),
                    chunk_count=stored_manifest.chunk_count,
                    loaded_from_cache=True,
                )

    rag_chunks = prepare_document_chunks(
        catalog=catalog,
        source_dir=source_dir,
        settings=settings,
    )
    new_vector_search = InMemoryVectorSearch(embedding=embedding)
    # 캐시 생성 흐름에서 문서 Embedding이 발생하는 유일한 지점이다.
    new_vector_search.add_chunks(rag_chunks)

    new_manifest = IndexManifest(
        version=INDEX_CACHE_VERSION,
        embedding_model=embedding_model_name,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        chunk_count=len(rag_chunks),
        catalog=catalog,
        source_hashes=current_source_hashes,
    )
    _write_cache(new_vector_search, new_manifest, vector_cache_path, manifest_path)
    return CachedVectorIndex(
        vector_search=new_vector_search,
        document_count=len(catalog),
        chunk_count=len(rag_chunks),
        loaded_from_cache=False,
    )


def _cache_is_valid(
    manifest: IndexManifest | None,
    *,
    cache_path: Path,
    embedding_model: str,
    settings: Settings,
    catalog: list[DocumentCatalogEntry],
    source_hashes: dict[str, str],
) -> bool:
    """현재 문서·설정과 저장된 manifest가 완전히 일치하는지 확인한다."""
    return (
        cache_path.is_file()
        and manifest is not None
        and manifest.version == INDEX_CACHE_VERSION
        and manifest.embedding_model == embedding_model
        and manifest.chunk_size == settings.chunk_size
        and manifest.chunk_overlap == settings.chunk_overlap
        and manifest.catalog == catalog
        and manifest.source_hashes == source_hashes
    )


def _source_hashes(
    catalog: list[DocumentCatalogEntry],
    source_dir: Path,
) -> dict[str, str]:
    """원본을 수정하지 않고 catalog PDF별 SHA-256을 계산한다."""
    source_hashes: dict[str, str] = {}
    for document_entry in catalog:
        source_path = source_dir / document_entry["file_name"]
        if not source_path.is_file():
            raise FileNotFoundError(f"PDF not found: {document_entry['file_name']}")
        sha256_digest = hashlib.sha256()
        with source_path.open("rb") as source_file:
            for file_block in iter(lambda: source_file.read(1024 * 1024), b""):
                sha256_digest.update(file_block)
        source_hashes[document_entry["file_name"]] = sha256_digest.hexdigest()
    return source_hashes


def _read_manifest(path: Path) -> IndexManifest | None:
    """manifest를 읽고 손상됐거나 형식이 맞지 않으면 None을 반환한다."""
    if not path.is_file():
        return None
    try:
        return IndexManifest(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_cache(
    vector_search: InMemoryVectorSearch,
    manifest: IndexManifest,
    cache_path: Path,
    manifest_path: Path,
) -> None:
    """Vector 인덱스와 manifest를 임시 파일에 쓴 뒤 원자적으로 교체한다."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_cache = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
    temporary_manifest = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")

    vector_search.save(temporary_cache)
    temporary_manifest.write_text(
        json.dumps(asdict(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_cache.replace(cache_path)
    temporary_manifest.replace(manifest_path)
