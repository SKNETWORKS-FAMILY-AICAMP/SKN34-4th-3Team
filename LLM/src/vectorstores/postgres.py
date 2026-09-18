import hashlib
from datetime import datetime

from langchain_core.embeddings import Embeddings
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.core.config import Settings
from src.core.database import connect_database
from src.data.contracts import RagChunk, VectorSearchResult


class PostgresVectorSearch:
    """실제 PostgreSQL `rag_documents`를 사용하는 pgvector 검색 구현체."""

    def __init__(self, embedding: Embeddings, settings: Settings) -> None:
        """Embedding 모델과 PostgreSQL 설정을 저장하고 Vector schema를 준비한다.

        Args:
            embedding: 문서와 Query를 1,536차원 벡터로 변환할 Embedding 구현체.
            settings: DATABASE_URL과 연결 제한시간을 담은 설정.
        """
        self._embedding = embedding
        self._settings = settings
        self.last_embedded_count = 0
        self._validate_chunk_schema()

    def add_chunks(
        self,
        chunks: list[RagChunk],
        *,
        force: bool = False,
        prune_missing: bool = True,
    ) -> list[str]:
        """변경되거나 새로 추가된 Chunk만 임베딩해 pgvector에 upsert한다.

        Args:
            chunks: 실제 DB 원천 데이터에서 생성한 RAG Chunk 목록.
            force: True이면 기존 hash와 관계없이 모든 Chunk를 다시 임베딩한다.
            prune_missing: 전체 원천 동기화일 때만 사라진 Chunk를 삭제한다.

        Returns:
            현재 원천 데이터에 존재하는 전체 Chunk ID 목록.

        Notes:
            `policies`와 `announcements` 원본은 읽거나 참조만 하며 수정하지 않는다.
        """
        if not chunks:
            self.last_embedded_count = 0
            return []

        chunk_hashes = {
            chunk["chunk_id"]: _content_hash(chunk["content"])
            for chunk in chunks
        }
        existing_hashes = self._existing_hashes()
        changed_chunks = [
            chunk
            for chunk in chunks
            if force
            or existing_hashes.get(chunk["chunk_id"])
            != chunk_hashes[chunk["chunk_id"]]
        ]
        embeddings = (
            self._embedding.embed_documents(
                [chunk["content"] for chunk in changed_chunks]
            )
            if changed_chunks
            else []
        )

        with connect_database(self._settings) as connection:
            register_vector(connection)
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO rag_documents (
                        source_type, source_id, embedding_status, embedding,
                        chunk_id, policy_id, content, updated_at
                    )
                    VALUES (
                        %s, %s, 'ready', %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (chunk_id) DO UPDATE SET
                        source_type = EXCLUDED.source_type,
                        source_id = EXCLUDED.source_id,
                        embedding_status = EXCLUDED.embedding_status,
                        embedding = EXCLUDED.embedding,
                        policy_id = EXCLUDED.policy_id,
                        content = EXCLUDED.content,
                        updated_at = now()
                    """,
                    [
                        (
                            chunk.get("source_type", "policy"),
                            chunk.get("source_id", chunk["policy_id"]),
                            vector,
                            chunk["chunk_id"],
                            chunk["policy_id"],
                            chunk["content"],
                        )
                        for chunk, vector in zip(
                            changed_chunks,
                            embeddings,
                            strict=True,
                        )
                    ],
                )
                if prune_missing:
                    source_types = sorted(
                        {chunk.get("source_type", "policy") for chunk in chunks}
                    )
                    cursor.execute(
                        """
                        DELETE FROM rag_documents
                        WHERE chunk_id IS NOT NULL
                          AND source_type = ANY(%s)
                          AND NOT (chunk_id = ANY(%s))
                        """,
                        (source_types, list(chunk_hashes)),
                    )

        self.last_embedded_count = len(changed_chunks)
        return list(chunk_hashes)

    def reindex_document_ids(
        self,
        document_ids: list[int],
        *,
        force: bool = False,
    ) -> list[int]:
        """기존 `rag_documents.id` 행만 선택해 다른 Chunk 삭제 없이 재색인한다."""
        requested_ids = list(dict.fromkeys(document_ids))
        if not requested_ids:
            return []
        with connect_database(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT id, chunk_id, policy_id, content, source_type, source_id
                    FROM rag_documents
                    WHERE id = ANY(%s)
                      AND chunk_id IS NOT NULL
                    ORDER BY id
                    """,
                    (requested_ids,),
                )
                rows = cursor.fetchall()
        found_ids = [int(row["id"]) for row in rows]
        missing_ids = sorted(set(requested_ids) - set(found_ids))
        if missing_ids:
            raise RagDocumentNotFoundError(
                "RAG documents not found: " + ", ".join(map(str, missing_ids))
            )
        chunks: list[RagChunk] = [
            {
                "chunk_id": str(row["chunk_id"]),
                "policy_id": (
                    int(row["policy_id"])
                    if row["policy_id"] is not None
                    else None
                ),
                "title": f"RAG 문서 {row['id']}",
                "source": f"db://{row['source_type']}/{row['source_id']}",
                "page": 1,
                "content": str(row["content"] or ""),
                "source_type": row["source_type"],
                "source_id": int(row["source_id"]),
            }
            for row in rows
        ]
        self.add_chunks(chunks, force=force, prune_missing=False)
        return found_ids

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Query Embedding과 cosine distance로 관련 Chunk를 검색한다.

        Args:
            query: Embedding할 사용자 질문 또는 개인화 Query.
            policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 정책 검색.
            top_k: 유사도 순서로 반환할 최대 Chunk 수.

        Returns:
            기존 Retriever schema와 호환되는 pgvector 검색 결과.

        Raises:
            ValueError: Query가 비었거나 top_k가 1보다 작을 때.
        """
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        query_embedding = Vector(self._embedding.embed_query(query))
        with connect_database(self._settings) as connection:
            register_vector(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        rd.id, rd.chunk_id, rd.policy_id,
                        COALESCE(p.title, td.title, '문서 ' || rd.source_id) AS title,
                        COALESCE(a.source_url, td.source,
                            'db://' || rd.source_type || '/' || rd.source_id) AS source,
                        1 AS page, rd.content, rd.source_type, rd.source_id,
                        1 - (rd.embedding <=> %s) AS score
                    FROM rag_documents AS rd
                    LEFT JOIN policies AS p ON rd.policy_id = p.id
                    LEFT JOIN announcements AS a
                      ON rd.source_type = 'announcement' AND rd.source_id = a.id
                    LEFT JOIN tax_documents AS td
                      ON rd.source_type = 'tax_document' AND rd.source_id = td.id
                    WHERE rd.embedding_status = 'ready'
                      AND rd.embedding IS NOT NULL
                      AND rd.chunk_id IS NOT NULL
                      AND (%s::integer IS NULL OR rd.policy_id = %s)
                      AND (%s::text[] IS NULL OR rd.source_type = ANY(%s::text[]))
                      AND (NOT %s OR rd.policy_id IS NOT NULL)
                    ORDER BY rd.embedding <=> %s
                    LIMIT %s
                    """,
                    (
                        query_embedding,
                        policy_id,
                        policy_id,
                        list(source_types) if source_types is not None else None,
                        list(source_types) if source_types is not None else None,
                        require_policy_id,
                        query_embedding,
                        top_k,
                    ),
                )
                rows = cursor.fetchall()
        return [_row_to_search_result(row) for row in rows]

    def get_chunks(self) -> list[RagChunk]:
        """BM25가 pgvector와 동일한 Chunk 집합을 사용하도록 전체 본문을 조회한다.

        Returns:
            `ready` 상태인 모든 정책·공고문 Chunk와 metadata.
        """
        with connect_database(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        rd.id, rd.chunk_id, rd.policy_id,
                        COALESCE(p.title, td.title, '문서 ' || rd.source_id) AS title,
                        COALESCE(a.source_url, td.source,
                            'db://' || rd.source_type || '/' || rd.source_id) AS source,
                        1 AS page, rd.content, rd.source_type, rd.source_id
                    FROM rag_documents AS rd
                    LEFT JOIN policies AS p ON rd.policy_id = p.id
                    LEFT JOIN announcements AS a
                      ON rd.source_type = 'announcement' AND rd.source_id = a.id
                    LEFT JOIN tax_documents AS td
                      ON rd.source_type = 'tax_document' AND rd.source_id = td.id
                    WHERE rd.embedding_status = 'ready'
                      AND rd.embedding IS NOT NULL
                      AND rd.chunk_id IS NOT NULL
                    ORDER BY rd.id
                    """
                )
                rows = cursor.fetchall()
        return [
            {
                "chunk_id": str(row["chunk_id"]),
                "policy_id": (
                    int(row["policy_id"]) if row["policy_id"] is not None else None
                ),
                "title": str(row["title"]),
                "source": str(row["source"]),
                "page": int(row["page"]),
                "content": str(row["content"]),
                "source_type": row["source_type"],
                "source_id": int(row["source_id"]),
                **({"id": int(row["id"])} if row["source_type"] == "tax_document" else {}),
            }
            for row in rows
        ]

    def get_tax_evidence_by_ids(
        self, ids: list[int], not_modified_after: datetime
    ) -> list[VectorSearchResult]:
        """Restore current, ready tax chunks by their existing rag_documents PKs."""
        if not ids:
            return []
        with connect_database(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT rd.id, rd.chunk_id, rd.policy_id,
                           COALESCE(td.title, '문서 ' || rd.source_id) AS title,
                           COALESCE(td.source,
                               'db://' || rd.source_type || '/' || rd.source_id) AS source,
                           1 AS page, rd.content, rd.source_type, rd.source_id,
                           1.0 AS score
                    FROM rag_documents AS rd
                    LEFT JOIN tax_documents AS td
                      ON rd.source_id = td.id
                    WHERE rd.id = ANY(%s)
                      AND rd.updated_at <= %s
                      AND rd.source_type = 'tax_document'
                      AND rd.embedding_status = 'ready'
                      AND rd.embedding IS NOT NULL
                      AND rd.chunk_id IS NOT NULL
                    """,
                    (ids, not_modified_after),
                )
                rows = cursor.fetchall()
        by_id = {int(row["id"]): _row_to_search_result(row) for row in rows}
        return [by_id[document_id] for document_id in ids if document_id in by_id]

    def counts(self) -> tuple[int, int]:
        """검색 가능한 원천 문서 수와 Chunk 수를 반환한다."""
        with connect_database(self._settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT (source_type, source_id)),
                        COUNT(*)
                    FROM rag_documents
                    WHERE embedding_status = 'ready'
                      AND embedding IS NOT NULL
                      AND chunk_id IS NOT NULL
                    """
                )
                document_count, chunk_count = cursor.fetchone()
        return int(document_count), int(chunk_count)

    def _existing_hashes(self) -> dict[str, str]:
        """기존 Chunk별 본문 hash와 Embedding 모델명을 조회한다."""
        with connect_database(self._settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_id, content
                    FROM rag_documents
                    WHERE chunk_id IS NOT NULL
                    """
                )
                return {
                    str(chunk_id): _content_hash(str(content or ""))
                    for chunk_id, content in cursor.fetchall()
                }

    def _validate_chunk_schema(self) -> None:
        """DB를 변경하지 않고 `rag_documents`의 필수 Chunk 컬럼을 확인한다."""
        required_columns = {
            "chunk_id",
            "policy_id",
            "content",
        }
        with connect_database(self._settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'rag_documents'
                    """
                )
                existing_columns = {str(row[0]) for row in cursor.fetchall()}

        missing_columns = sorted(required_columns - existing_columns)
        if missing_columns:
            raise RuntimeError(
                "rag_documents schema is missing required chunk columns: "
                + ", ".join(missing_columns)
                )


def _content_hash(content: str) -> str:
    """Chunk 본문의 SHA-256 hash를 계산한다."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class RagDocumentNotFoundError(LookupError):
    """부분 재색인에서 요청한 `rag_documents.id`를 찾지 못했을 때 발생한다."""


def _row_to_search_result(row: dict[str, object]) -> VectorSearchResult:
    """PostgreSQL 검색 행을 기존 Retriever 결과로 변환한다."""
    return {
        "chunk_id": str(row["chunk_id"]),
        "policy_id": int(row["policy_id"]) if row["policy_id"] is not None else None,
        "title": str(row["title"]),
        "source": str(row["source"]),
        "page": int(row["page"]),
        "content": str(row["content"]),
        "score": float(row["score"]),
        "source_type": str(row["source_type"]),
        "source_id": int(row["source_id"]),
        **({"id": int(row["id"])} if row["source_type"] == "tax_document" else {}),
    }
