from collections.abc import Mapping
from html import unescape
import re
from typing import Any
import unicodedata

from psycopg.rows import dict_row

from src.core.config import Settings
from src.core.database import connect_database
from src.data.contracts import (
    CleanTaxDocument,
    CleanPolicy,
    Policy,
    PolicyRow,
    PreparedPolicy,
    PreparedTaxDocument,
    RagSourceDocument,
    UserProfile,
    TaxDocumentRow,
)


_HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_BULLET_PATTERN = re.compile(r"[○●■▶◆◇▪▫•◦ㅇ☞ㆍ▷▸▹]+")
_REPEATED_FORMATTING_PATTERN = re.compile(r"([_=※])\1{2,}")
_SPACED_LABEL_PATTERNS = (
    (re.compile(r"지\s+원\s+대\s+상"), "지원대상"),
    (re.compile(r"지\s+원\s+내\s+용"), "지원내용"),
    (re.compile(r"신\s+청\s+방\s+법"), "신청방법"),
    (re.compile(r"신\s+청\s+기\s+간"), "신청기간"),
)
_CIRCLED_NUMBERS = str.maketrans(
    {character: f"{number}. " for number, character in enumerate("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳", start=1)}
)
_POLICY_CONTENT_FIELDS = (
    ("title", "정책명"),
    ("region", "지역"),
    ("industry", "분야"),
    ("target", "지원대상"),
    ("benefit", "지원내용"),
)
_TAX_CONTENT_FIELDS = (
    ("title", "문서명"),
    ("law_name", "법령명"),
    ("content", "내용"),
)


class DatabaseDataNotFoundError(LookupError):
    """실제 PostgreSQL에 요청한 데이터가 없을 때 발생한다."""


def load_policies(settings: Settings) -> list[PolicyRow]:
    """PostgreSQL의 정책 원본을 변경하지 않고 필요한 컬럼만 조회한다.

    Args:
        settings: PostgreSQL 연결 설정.

    Returns:
        id, title, region, industry, target, benefit을 담은 정책 레코드 목록.
    """
    with connect_database(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT id, title, region, industry, target, benefit
                FROM policies
                ORDER BY id
                """
            )
            return [PolicyRow(**row) for row in cursor.fetchall()]


def clean_text(value: object | None) -> str | None:
    """Embedding 의미를 유지하면서 크롤링·문서 서식 노이즈를 정규화한다.

    Args:
        value: 정제할 DB 문자열 값 또는 None.

    Returns:
        HTML·제어문자·과도한 공백과 서식기호를 정리한 문자열. 유효한 내용이
        없으면 None.
    """
    if value is None:
        return None

    text = unescape(str(value)).replace("\ufffd", "")
    text = text.replace("\\r", " ").replace("\\n", " ").replace("\\t", " ")
    text = _HTML_COMMENT_PATTERN.sub(" ", text)
    text = _HTML_TAG_PATTERN.sub(" ", text)
    text = text.translate(_CIRCLED_NUMBERS)
    text = "".join(
        character
        for character in text
        if unicodedata.category(character) not in {"Cc", "Cf"}
        or character in "\r\n\t"
    )
    text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    text = _BULLET_PATTERN.sub(" - ", text)
    text = _REPEATED_FORMATTING_PATTERN.sub(r"\1", text)
    for label_pattern, normalized_label in _SPACED_LABEL_PATTERNS:
        text = label_pattern.sub(normalized_label, text)
    text = re.sub(r"(?:\s*-\s*){2,}", " - ", text)
    normalized_text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    if normalized_text.startswith("- "):
        normalized_text = normalized_text[2:].strip()
    return normalized_text or None


def clean_policy(policy_row: Mapping[str, object | None]) -> CleanPolicy:
    """정책 ID를 유지하고 모든 검색 대상 문자열을 동일 규칙으로 정제한다.

    Args:
        policy_row: `policies` SELECT 결과와 호환되는 Mapping.

    Returns:
        정책 ID와 정제된 title, region, industry, target, benefit.

    Raises:
        ValueError: 정책 ID가 없거나 정수로 변환할 수 없을 때.
    """
    policy_id = policy_row.get("id")
    if policy_id is None:
        raise ValueError("Policy row must contain id")
    return {
        "policy_id": int(policy_id),
        "title": clean_text(policy_row.get("title")),
        "region": clean_text(policy_row.get("region")),
        "industry": clean_text(policy_row.get("industry")),
        "target": clean_text(policy_row.get("target")),
        "benefit": clean_text(policy_row.get("benefit")),
    }


def build_policy_content(cleaned_policy: CleanPolicy) -> str:
    """정제된 정책 필드에 의미 라벨을 붙여 RAG 검색용 본문을 생성한다.

    Args:
        cleaned_policy: `clean_policy()`가 반환한 정제 정책.

    Returns:
        값이 존재하는 필드만 줄 단위로 결합한 검색용 문자열.
    """
    return "\n".join(
        f"{label}: {value}"
        for field_name, label in _POLICY_CONTENT_FIELDS
        if (value := cleaned_policy[field_name])
    )


def prepare_policies(settings: Settings) -> list[PreparedPolicy]:
    """실제 정책을 조회·정제해 Chunking 직전 RAG 데이터로 변환한다.

    Args:
        settings: PostgreSQL 연결 설정.

    Returns:
        policy_id, 검색용 content와 최소 metadata를 담은 정책 목록.
    """
    prepared_policies: list[PreparedPolicy] = []
    for policy_row in load_policies(settings):
        cleaned_policy = clean_policy(policy_row)
        content = build_policy_content(cleaned_policy)
        if not content:
            continue
        metadata = {
            field_name: value
            for field_name in ("title", "region", "industry")
            if (value := cleaned_policy[field_name])
        }
        prepared_policies.append(
            {
                "policy_id": cleaned_policy["policy_id"],
                "content": content,
                "metadata": metadata,
            }
        )
    return prepared_policies


def load_tax_documents(settings: Settings) -> list[TaxDocumentRow]:
    """세법 원본을 변경하지 않고 정제에 필요한 컬럼만 조회한다."""
    with connect_database(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT id, title, law_name, content, source
                FROM tax_documents
                ORDER BY id
                """
            )
            return [TaxDocumentRow(**row) for row in cursor.fetchall()]


def clean_tax_document(
    tax_document_row: Mapping[str, object | None],
) -> CleanTaxDocument:
    """세법 문서의 모든 문자열 필드에 정책과 동일한 정제 규칙을 적용한다."""
    tax_document_id = tax_document_row.get("id")
    if tax_document_id is None:
        raise ValueError("Tax document row must contain id")
    return {
        "tax_document_id": int(tax_document_id),
        "title": clean_text(tax_document_row.get("title")),
        "law_name": clean_text(tax_document_row.get("law_name")),
        "content": clean_text(tax_document_row.get("content")),
        "source": clean_text(tax_document_row.get("source")),
    }


def build_tax_document_content(cleaned_document: CleanTaxDocument) -> str:
    """정제된 세법 필드를 검색용 본문으로 결합한다."""
    return "\n".join(
        f"{label}: {value}"
        for field_name, label in _TAX_CONTENT_FIELDS
        if (value := cleaned_document[field_name])
    )


def prepare_tax_documents(settings: Settings) -> list[PreparedTaxDocument]:
    """세법 문서를 조회·정제해 Chunking 직전 데이터로 변환한다."""
    prepared_documents: list[PreparedTaxDocument] = []
    for row in load_tax_documents(settings):
        cleaned_document = clean_tax_document(row)
        content = build_tax_document_content(cleaned_document)
        if not content:
            continue
        metadata = {
            field_name: value
            for field_name in ("title", "law_name", "source")
            if (value := cleaned_document[field_name])
        }
        prepared_documents.append(
            {
                "tax_document_id": cleaned_document["tax_document_id"],
                "content": content,
                "metadata": metadata,
            }
        )
    return prepared_documents


def get_user_profile(user_id: int, settings: Settings) -> UserProfile:
    """PostgreSQL에서 사용자와 사업자 프로필을 함께 조회한다.

    Args:
        user_id: 조회할 실제 사용자 식별자.
        settings: PostgreSQL 연결 설정.

    Returns:
        RAG 개인화 Query에서 사용하는 사용자·사업자 정보.

    Raises:
        DatabaseDataNotFoundError: 사용자 또는 사업자 프로필이 없을 때.
    """
    with connect_database(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    u.id AS user_id,
                    u.age,
                    u.region,
                    bp.industry,
                    bp.business_type,
                    bp.business_registered_at,
                    bp.founded_at
                FROM users AS u
                JOIN business_profiles AS bp ON bp.user_id = u.id
                WHERE u.id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise DatabaseDataNotFoundError(
            f"User or business profile not found: {user_id}"
        )
    founded_at = row["founded_at"]
    business_registered_at = row["business_registered_at"]
    return {
        "user_id": int(row["user_id"]),
        "age": int(row["age"]) if row["age"] is not None else None,
        "region": row["region"],
        "business": {
            "industry": row["industry"],
            "business_type": row["business_type"],
            "business_registered_at": (
                business_registered_at.isoformat() if business_registered_at else None
            ),
            "founded_at": founded_at.isoformat() if founded_at else None,
        },
    }


def get_policy(policy_id: int, settings: Settings) -> Policy:
    """PostgreSQL에서 정책과 최신 공고의 신청기간을 조회한다.

    Args:
        policy_id: 조회할 실제 정책 식별자.
        settings: PostgreSQL 연결 설정.

    Returns:
        정책 기본 정보와 최신 공고 신청기간.

    Raises:
        DatabaseDataNotFoundError: 해당 정책이 없을 때.
    """
    with connect_database(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    p.id AS policy_id,
                    p.title,
                    p.region,
                    p.industry,
                    latest.apply_start_date,
                    latest.apply_end_date
                FROM policies AS p
                LEFT JOIN LATERAL (
                    SELECT apply_start_date, apply_end_date
                    FROM announcements
                    WHERE policy_id = p.id
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                ) AS latest ON TRUE
                WHERE p.id = %s
                """,
                (policy_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise DatabaseDataNotFoundError(f"Policy not found: {policy_id}")
    industry = str(row["industry"] or "").strip()
    return {
        "policy_id": int(row["policy_id"]),
        "title": str(row["title"]),
        "region": str(row["region"] or ""),
        "industry": [industry] if industry else [],
        "apply_start_date": _date_text(row["apply_start_date"]),
        "apply_end_date": _date_text(row["apply_end_date"]),
    }


def get_policy_source_documents(settings: Settings) -> list[RagSourceDocument]:
    """정책과 공고문을 수정하지 않고 RAG 원천 문서로 조회한다.

    Args:
        settings: PostgreSQL 연결 설정.

    Returns:
        정책 ID와 원천 유형이 포함된 정책·공고문 문서 목록.
    """
    policy_rows = load_policies(settings)
    with connect_database(settings) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT a.id, a.policy_id, p.title, a.raw_content,
                       a.source_url, a.apply_start_date, a.apply_end_date
                FROM announcements AS a
                JOIN policies AS p ON p.id = a.policy_id
                WHERE NULLIF(BTRIM(a.raw_content), '') IS NOT NULL
                ORDER BY a.id
                """
            )
            announcement_rows = cursor.fetchall()

    return [
        _policy_source_document(row) for row in policy_rows
    ] + [
        _announcement_source_document(row) for row in announcement_rows
    ]


def get_rag_source_documents(settings: Settings) -> list[RagSourceDocument]:
    """정제된 정책·공고·세법 문서를 하나의 RAG 원천 목록으로 조회한다.

    Args:
        settings: PostgreSQL 연결 설정.

    Returns:
        Chunking과 Embedding에 사용할 전체 DB 원천 문서.
    """
    policy_documents = get_policy_source_documents(settings)
    tax_documents = [
        _tax_source_document(row) for row in load_tax_documents(settings)
    ]
    return policy_documents + tax_documents


def _tax_source_document(row: Mapping[str, Any]) -> RagSourceDocument:
    """세법 레코드를 정책과 같은 정제 규칙을 거친 RAG 문서로 변환한다."""
    cleaned_document = clean_tax_document(row)
    document_id = cleaned_document["tax_document_id"]
    return {
        "source_type": "tax_document",
        "source_id": document_id,
        "policy_id": None,
        "title": cleaned_document["title"] or f"세법 문서 {document_id}",
        "source": cleaned_document["source"] or f"db://tax_documents/{document_id}",
        "content": build_tax_document_content(cleaned_document),
    }


def _policy_source_document(row: Mapping[str, Any]) -> RagSourceDocument:
    """정책 레코드를 검색 가능한 설명 문서로 변환한다."""
    cleaned_policy = clean_policy(row)
    policy_id = cleaned_policy["policy_id"]
    return {
        "source_type": "policy",
        "source_id": policy_id,
        "policy_id": policy_id,
        "title": cleaned_policy["title"] or f"정책 {policy_id}",
        "source": f"db://policies/{policy_id}",
        "content": build_policy_content(cleaned_policy),
    }


def _announcement_source_document(row: Mapping[str, Any]) -> RagSourceDocument:
    """공고문 레코드를 정책 ID가 포함된 검색 문서로 변환한다."""
    announcement_id = int(row["id"])
    return {
        "source_type": "announcement",
        "source_id": announcement_id,
        "policy_id": int(row["policy_id"]),
        "title": str(row["title"]),
        "source": str(
            row["source_url"] or f"db://announcements/{announcement_id}"
        ),
        "content": _join_labeled_values(
            ("정책명", row["title"]),
            ("신청 시작일", row["apply_start_date"]),
            ("신청 종료일", row["apply_end_date"]),
            ("공고 내용", row["raw_content"]),
        ),
    }


def _join_labeled_values(*items: tuple[str, object | None]) -> str:
    """값이 존재하는 DB 필드를 `항목: 값` 형식으로 결합한다."""
    return "\n".join(
        f"{label}: {value}"
        for label, value in items
        if value is not None and str(value).strip()
    )


def _date_text(value: object | None) -> str:
    """선택적 날짜 값을 기존 문자열 계약으로 변환한다."""
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
