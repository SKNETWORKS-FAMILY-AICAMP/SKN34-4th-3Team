"""RAG 데이터 계약, 임시 catalog와 Mock 데이터 접근 함수."""

from src.data.document_catalog import get_document_catalog
from src.data.mock_repository import (
    MockDataNotFoundError,
    get_eligibility_result,
    get_policy,
    get_rag_chunks,
    get_user_profile,
)
from src.data.postgres_repository import (
    build_tax_document_content,
    build_policy_content,
    clean_policy,
    clean_text,
    clean_tax_document,
    get_rag_source_documents,
    load_policies,
    load_tax_documents,
    prepare_policies,
    prepare_tax_documents,
)

__all__ = [
    "MockDataNotFoundError",
    "build_policy_content",
    "build_tax_document_content",
    "clean_policy",
    "clean_text",
    "clean_tax_document",
    "get_eligibility_result",
    "get_document_catalog",
    "get_policy",
    "get_rag_chunks",
    "get_rag_source_documents",
    "get_user_profile",
    "load_policies",
    "load_tax_documents",
    "prepare_policies",
    "prepare_tax_documents",
]
