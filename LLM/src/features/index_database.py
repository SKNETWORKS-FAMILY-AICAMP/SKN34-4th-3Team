"""정제된 PostgreSQL 원천 문서를 pgvector에 적재하는 CLI 진입점."""

import argparse

from src.core.config import get_settings
from src.features.indexing import load_or_build_postgres_index
from src.models import get_embedding_model


def main() -> None:
    """정책·공고·세법을 정제·분할·임베딩하여 ``rag_documents``에 적재한다."""
    parser = argparse.ArgumentParser(description="DB 문서를 pgvector에 적재합니다.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="본문 변경 여부와 관계없이 모든 Chunk를 다시 임베딩합니다.",
    )
    args = parser.parse_args()

    settings = get_settings()
    if settings.vector_store_backend != "postgres":
        raise RuntimeError("VECTOR_STORE_BACKEND must be 'postgres'")

    result = load_or_build_postgres_index(
        embedding=get_embedding_model(),
        settings=settings,
        force=args.force,
    )
    print(
        f"documents={result.document_count} chunks={result.chunk_count} "
        f"embedded={result.vector_search.last_embedded_count}"
    )


if __name__ == "__main__":
    main()
