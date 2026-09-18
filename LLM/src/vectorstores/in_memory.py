from pathlib import Path

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from src.data.contracts import RagChunk, VectorSearchResult


class InMemoryVectorSearch:
    """pgvector 준비 전 사용하는 프로세스 내부 Vector Search 구현체."""

    def __init__(self, embedding: Embeddings) -> None:
        """In-memory Vector Store를 초기화한다.

        Args:
            embedding: 문서와 Query를 같은 벡터 공간으로 변환할 Embedding 구현체.
        """
        self._vector_store = InMemoryVectorStore(embedding=embedding)

    def add_chunks(self, chunks: list[RagChunk]) -> list[str]:
        """입력 Dictionary를 변경하지 않고 Chunk를 임베딩·저장한다.

        Args:
            chunks: 본문과 정책·출처 metadata가 포함된 RAG Chunk 목록.

        Returns:
            Vector Store에 저장된 Chunk ID 목록.

        Notes:
            이 함수에서 Embedding 구현체의 `embed_documents()`가 호출된다.
        """
        langchain_documents = [self._to_document(chunk) for chunk in chunks]
        chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        return self._vector_store.add_documents(
            documents=langchain_documents,
            ids=chunk_ids,
        )

    def save(self, path: Path) -> None:
        """프로세스 내부 Vector Store를 다음 실행에서 쓸 파일로 저장한다.

        Args:
            path: 직렬화된 Vector 인덱스를 저장할 경로.
        """
        self._vector_store.dump(str(path))

    def get_chunks(self) -> list[RagChunk]:
        """Dense 저장소에 적재된 모든 Chunk의 복사본을 반환한다.

        Returns:
            BM25 등 다른 검색 방식에서 동일하게 사용할 RAG Chunk 목록.
        """
        return [
            {
                "chunk_id": str(stored_document["metadata"]["chunk_id"]),
                "policy_id": (
                    int(stored_document["metadata"]["policy_id"])
                    if stored_document["metadata"]["policy_id"] is not None else None
                ),
                "title": str(stored_document["metadata"]["title"]),
                "source": str(stored_document["metadata"]["source"]),
                "page": int(stored_document["metadata"]["page"]),
                "content": str(stored_document["text"]),
                **({"source_type": stored_document["metadata"]["source_type"]}
                   if "source_type" in stored_document["metadata"] else {}),
                **({"source_id": stored_document["metadata"]["source_id"]}
                   if "source_id" in stored_document["metadata"] else {}),
            }
            for stored_document in self._vector_store.store.values()
        ]

    @classmethod
    def load(cls, path: Path, *, embedding: Embeddings) -> "InMemoryVectorSearch":
        """원본 문서를 다시 임베딩하지 않고 로컬 Vector 인덱스를 복원한다.

        Args:
            path: 저장된 Vector 인덱스 파일 경로.
            embedding: 이후 Query Embedding에 사용할 모델 구현체.

        Returns:
            로컬 캐시에서 복원한 InMemoryVectorSearch 객체.
        """
        vector_search = cls(embedding=embedding)
        vector_search._vector_store = InMemoryVectorStore.load(
            str(path),
            embedding=embedding,
        )
        return vector_search

    def search(
        self,
        query: str,
        *,
        policy_id: int | None = None,
        source_types: tuple[str, ...] | None = None,
        require_policy_id: bool = False,
        top_k: int = 5,
    ) -> list[VectorSearchResult]:
        """Query와 유사한 Chunk를 관련성 순서로 검색한다.

        Args:
            query: Embedding하고 유사도 검색할 질문 또는 개인화 Query.
            policy_id: 특정 정책으로 검색 범위를 제한할 ID. None이면 전체 검색.
            source_types: Dense 후보를 뽑기 전에 적용할 원천 문서 유형.
            require_policy_id: True이면 정책 ID가 연결된 Chunk만 검색한다.
            top_k: 반환할 최대 Chunk 개수.

        Returns:
            원래 metadata와 유사도 점수를 포함한 검색 결과 목록.

        Raises:
            ValueError: Query가 비었거나 top_k가 1보다 작을 때.
        """
        if not query.strip():
            raise ValueError("query must not be blank")
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        document_filter = None
        if policy_id is not None or source_types is not None or require_policy_id:
            document_filter = lambda document: (
                (policy_id is None or document.metadata.get("policy_id") == policy_id)
                and (source_types is None or (
                    document.metadata.get("source_type") or (
                        "policy" if document.metadata.get("policy_id") is not None
                        else "tax_document"
                    )
                ) in source_types)
                and (not require_policy_id or document.metadata.get("policy_id") is not None)
            )

        scored_documents = self._vector_store.similarity_search_with_score(
            query=query,
            k=top_k,
            filter=document_filter,
        )
        return [
            self._to_search_result(document, similarity_score)
            for document, similarity_score in scored_documents
        ]

    @staticmethod
    def _to_document(chunk: RagChunk) -> Document:
        """RAG Chunk를 LangChain Document로 변환한다."""
        return Document(
            id=chunk["chunk_id"],
            page_content=chunk["content"],
            metadata={
                "chunk_id": chunk["chunk_id"],
                "policy_id": chunk["policy_id"],
                "title": chunk["title"],
                "source": chunk["source"],
                "page": chunk["page"],
                **({"source_type": chunk["source_type"]} if "source_type" in chunk else {}),
                **({"source_id": chunk["source_id"]} if "source_id" in chunk else {}),
            },
        )

    @staticmethod
    def _to_search_result(document: Document, score: float) -> VectorSearchResult:
        """점수가 포함된 LangChain Document를 공통 검색 결과로 변환한다."""
        document_metadata = document.metadata
        return {
            "chunk_id": str(document_metadata["chunk_id"]),
            "policy_id": (
                int(document_metadata["policy_id"])
                if document_metadata["policy_id"] is not None else None
            ),
            "title": str(document_metadata["title"]),
            "source": str(document_metadata["source"]),
            "page": int(document_metadata["page"]),
            "content": document.page_content,
            "score": float(score),
            **({"source_type": document_metadata["source_type"]}
               if "source_type" in document_metadata else {}),
            **({"source_id": document_metadata["source_id"]}
               if "source_id" in document_metadata else {}),
        }
