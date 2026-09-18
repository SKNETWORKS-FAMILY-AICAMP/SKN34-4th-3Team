import argparse

from src.core.config import get_settings
from src.data import get_document_catalog
from src.features.document_processing import PdfDocumentError
from src.features.indexing import load_or_build_document_index
from src.models import ModelConfigurationError, get_embedding_model


def build_parser() -> argparse.ArgumentParser:
    """문서 인덱싱 CLI의 argument parser를 생성한다.

    Returns:
        Query, 정책 필터, top-k와 강제 재생성 옵션이 등록된 parser.
    """
    argument_parser = argparse.ArgumentParser(
        description="Embed source PDFs into a temporary in-memory vector index."
    )
    argument_parser.add_argument("--query", help="Optional query to run after indexing")
    argument_parser.add_argument(
        "--policy-id", type=int, help="Optional policy metadata filter"
    )
    argument_parser.add_argument("--top-k", type=int, help="Number of search results")
    argument_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore a valid local cache and embed all documents again",
    )
    return argument_parser


def main() -> None:
    """로컬 캐시를 우선 사용해 PDF 인덱스를 준비하고 선택적으로 검색한다.

    Raises:
        SystemExit: 설정, 원본 PDF 또는 Chunking 값이 잘못됐을 때.

    Notes:
        캐시가 무효이거나 `--force`를 사용하면 실제 문서 Embedding API가 호출된다.
    """
    cli_arguments = build_parser().parse_args()
    settings = get_settings()

    try:
        document_catalog = get_document_catalog()
        cached_vector_index = load_or_build_document_index(
            embedding=get_embedding_model(),
            settings=settings,
            catalog=document_catalog,
            force=cli_arguments.force,
        )
    except (
        FileNotFoundError,
        ModelConfigurationError,
        PdfDocumentError,
        ValueError,
    ) as exc:
        raise SystemExit(f"Document indexing failed: {exc}") from exc

    index_source_label = (
        "local cache" if cached_vector_index.loaded_from_cache else "new embedding"
    )
    print(
        f"Loaded {cached_vector_index.document_count} documents and "
        f"{cached_vector_index.chunk_count} chunks from {index_source_label}."
    )
    print("The in-memory copy will be discarded; the validated local cache remains.")

    if not cli_arguments.query:
        return

    result_limit = (
        cli_arguments.top_k
        if cli_arguments.top_k is not None
        else settings.default_top_k
    )
    search_results = cached_vector_index.vector_search.search(
        cli_arguments.query,
        policy_id=cli_arguments.policy_id,
        top_k=result_limit,
    )
    if not search_results:
        print("No matching chunks found.")
        return

    for rank, search_result in enumerate(search_results, start=1):
        content_preview = " ".join(search_result["content"].split())[:160]
        print(
            f"[{rank}] policy={search_result['policy_id']} "
            f"page={search_result['page']} score={search_result['score']:.4f} "
            f"source={search_result['source']}"
        )
        print(f"    {content_preview}")


if __name__ == "__main__":
    main()
