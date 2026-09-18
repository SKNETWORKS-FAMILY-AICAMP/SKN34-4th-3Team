from typing import Literal, NotRequired, TypedDict


class BusinessProfile(TypedDict):
    """사업자 정보 JSON 구조."""

    industry: str | None
    business_type: str | None
    founded_at: str | None
    business_registered_at: NotRequired[str | None]


class UserProfile(TypedDict):
    """사용자와 사업자 정보를 결합한 JSON 구조."""

    user_id: int
    age: int | None
    region: str | None
    business: BusinessProfile


class Policy(TypedDict):
    """정책 기본 정보 JSON 구조."""

    policy_id: int
    title: str
    region: str
    industry: list[str]
    apply_start_date: str
    apply_end_date: str


class PolicyRow(TypedDict):
    """PostgreSQL `policies`에서 읽은 정제 전 레코드 구조."""

    id: int
    title: str | None
    region: str | None
    industry: str | None
    target: str | None
    benefit: str | None


class CleanPolicy(TypedDict):
    """검색 의미를 보존하면서 문자열 노이즈를 제거한 정책 구조."""

    policy_id: int
    title: str | None
    region: str | None
    industry: str | None
    target: str | None
    benefit: str | None


class PreparedPolicy(TypedDict):
    """Chunking과 Embedding 직전 단계의 RAG 정책 구조."""

    policy_id: int
    content: str
    metadata: dict[str, str]


class TaxDocumentRow(TypedDict):
    """PostgreSQL ``tax_documents``에서 조회한 원본 레코드."""

    id: int
    title: str | None
    law_name: str | None
    content: str | None
    source: str | None


class CleanTaxDocument(TypedDict):
    """정책과 동일한 텍스트 규칙으로 정제한 세법 문서."""

    tax_document_id: int
    title: str | None
    law_name: str | None
    content: str | None
    source: str | None


class PreparedTaxDocument(TypedDict):
    """Chunking과 Embedding 직전 단계의 세법 문서."""

    tax_document_id: int
    content: str
    metadata: dict[str, str]


class EligibilityResult(TypedDict):
    """Backend가 계산한 정책 자격 판정 결과 구조."""

    question: str
    policy_id: int
    eligible: bool
    reasons: list[str]


class RagChunk(TypedDict):
    """Embedding과 검색에 사용하는 RAG Chunk 구조."""

    chunk_id: str
    policy_id: int | None
    title: str
    source: str
    page: int
    content: str
    source_type: NotRequired[Literal["policy", "announcement", "tax_document"]]
    source_id: NotRequired[int]
    id: NotRequired[int]


class RagSourceDocument(TypedDict):
    """실제 DB 원천 레코드를 Chunking하기 위한 공통 문서 구조."""

    source_type: Literal["policy", "announcement", "tax_document"]
    source_id: int
    policy_id: int | None
    title: str
    source: str
    content: str


class VectorSearchResult(RagChunk):
    """RAG Chunk에 유사도 점수가 추가된 검색 결과 구조."""

    score: float


class DocumentCatalogEntry(TypedDict):
    """원본 PDF와 정책 ID를 연결하는 catalog 항목 구조."""

    policy_id: int
    title: str
    file_name: str
