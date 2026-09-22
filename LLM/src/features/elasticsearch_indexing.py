from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
import logging
import re
from typing import Any, TypedDict

from elasticsearch import Elasticsearch, helpers
from psycopg.rows import dict_row

from src.core.config import Settings, get_settings
from src.core.database import connect_database


logger = logging.getLogger(__name__)
_SAFE_INDEX_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_MANAGED_INDEX_SUFFIX = "-nori-v3-xsv-xsa-"
_ORPHAN_GRACE_PERIOD = timedelta(days=1)
# 조사·어미·접속어·기호와 의미가 어근에 남는 파생 접미사만 제거한다.
# 세금·법령 검색의 부정/범위 의미를 보존하기 위해 VX, VCN, MAG, MM, XPN, XSN은
# 제거하지 않는다.
NORI_SEARCH_STOP_TAGS = (
    "EC",
    "EF",
    "EP",
    "ETM",
    "ETN",
    "IC",
    "JC",
    "JKB",
    "JKC",
    "JKG",
    "JKO",
    "JKQ",
    "JKS",
    "JKV",
    "JX",
    "MAJ",
    "SC",
    "SE",
    "SF",
    "SP",
    "SSC",
    "SSO",
    "SY",
    "XSA",
    "XSV",
)


class ElasticsearchSourceDocument(TypedDict):
    """PostgreSQL 원본 테이블에서 읽은 Elasticsearch 색인 문서."""

    document_id: str
    source_type: str
    source_id: int
    policy_id: int | None
    title: str
    source: str
    content: str


class ElasticsearchReindexResult(TypedDict):
    """전체 재색인 결과."""

    index: str
    alias: str
    indexed_count: int


def nori_index_definition() -> dict[str, Any]:
    """Nori 형태소 분석기와 RAG 청크 mapping을 반환한다.

    Returns:
        제목과 본문에 Nori를 적용하고 식별자·필터 필드는 keyword/long으로
        보존하는 Elasticsearch index 정의.
    """
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "tokenizer": {
                    "korean_nori_tokenizer": {
                        "type": "nori_tokenizer",
                        "decompound_mode": "mixed",
                    }
                },
                "filter": {
                    "korean_search_pos": {
                        "type": "nori_part_of_speech",
                        "stoptags": list(NORI_SEARCH_STOP_TAGS),
                    }
                },
                "analyzer": {
                    "korean_nori_index_analyzer": {
                        "type": "custom",
                        "tokenizer": "korean_nori_tokenizer",
                        "char_filter": ["html_strip"],
                        "filter": ["lowercase", "nori_readingform"],
                    },
                    "korean_nori_search_analyzer": {
                        "type": "custom",
                        "tokenizer": "korean_nori_tokenizer",
                        "filter": [
                            "korean_search_pos",
                            "lowercase",
                            "nori_readingform",
                        ],
                    }
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "document_id": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "source_id": {"type": "long"},
                "policy_id": {"type": "long"},
                "title": {
                    "type": "text",
                    "analyzer": "korean_nori_index_analyzer",
                    "search_analyzer": "korean_nori_search_analyzer",
                    "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
                },
                "content": {
                    "type": "text",
                    "analyzer": "korean_nori_index_analyzer",
                    "search_analyzer": "korean_nori_search_analyzer",
                },
                "source": {"type": "keyword", "ignore_above": 2048},
            },
        },
    }


def load_elasticsearch_source_documents(
    settings: Settings,
) -> list[ElasticsearchSourceDocument]:
    """PostgreSQL 원본 데이터를 Elasticsearch 적재 형태로 직접 조회한다.

    Args:
        settings: PostgreSQL 연결 설정.

    Returns:
        정책·공고·세법 원본 레코드를 검색 문서로 변환한 목록.

    Notes:
        ``rag_documents``나 기존 RAG 재색인 함수를 사용하지 않는다. 원본 테이블에는
        SELECT만 수행하며 Nori 분석은 Elasticsearch가 색인 시점에 적용한다.
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
            policy_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT a.id, a.policy_id, p.title, a.raw_content, a.source_url,
                       a.apply_start_date, a.apply_end_date
                FROM announcements AS a
                JOIN policies AS p ON p.id = a.policy_id
                ORDER BY a.id
                """
            )
            announcement_rows = cursor.fetchall()
            cursor.execute(
                """
                SELECT id, title, law_name, content, source
                FROM tax_documents
                ORDER BY id
                """
            )
            tax_rows = cursor.fetchall()

    documents: list[ElasticsearchSourceDocument] = []
    for row in policy_rows:
        source_id = int(row["id"])
        documents.append(
            {
                "document_id": f"policy-{source_id}",
                "source_type": "policy",
                "source_id": source_id,
                "policy_id": source_id,
                "title": _text(row["title"], f"정책 {source_id}"),
                "source": f"db://policies/{source_id}",
                "content": _labeled_content(
                    ("정책명", row["title"]),
                    ("지역", row["region"]),
                    ("분야", row["industry"]),
                    ("지원대상", row["target"]),
                    ("지원내용", row["benefit"]),
                ),
            }
        )
    for row in announcement_rows:
        source_id = int(row["id"])
        documents.append(
            {
                "document_id": f"announcement-{source_id}",
                "source_type": "announcement",
                "source_id": source_id,
                "policy_id": int(row["policy_id"]),
                "title": _text(row["title"], f"공고 {source_id}"),
                "source": _text(
                    row["source_url"], f"db://announcements/{source_id}"
                ),
                "content": _labeled_content(
                    ("정책명", row["title"]),
                    ("신청 시작일", row["apply_start_date"]),
                    ("신청 종료일", row["apply_end_date"]),
                    ("공고 내용", row["raw_content"]),
                ),
            }
        )
    for row in tax_rows:
        source_id = int(row["id"])
        documents.append(
            {
                "document_id": f"tax_document-{source_id}",
                "source_type": "tax_document",
                "source_id": source_id,
                "policy_id": None,
                "title": _text(row["title"], f"세법 문서 {source_id}"),
                "source": _text(row["source"], f"db://tax_documents/{source_id}"),
                "content": _labeled_content(
                    ("문서명", row["title"]),
                    ("법령명", row["law_name"]),
                    ("내용", row["content"]),
                ),
            }
        )
    return [document for document in documents if document["content"]]


def iter_bulk_actions(
    documents: list[ElasticsearchSourceDocument], index_name: str
) -> Iterator[dict[str, Any]]:
    """조회한 DB 원본 문서를 Elasticsearch Bulk action으로 변환한다."""
    for document in documents:
        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": document["document_id"],
            "_source": dict(document),
        }


def _text(value: object | None, fallback: str) -> str:
    """DB 값을 문자열로 변환하고 비어 있으면 fallback을 반환한다."""
    normalized = str(value).strip() if value is not None else ""
    return normalized or fallback


def _labeled_content(*items: tuple[str, object | None]) -> str:
    """검색할 DB 필드를 의미 라벨과 함께 본문으로 결합한다."""
    return "\n".join(
        f"{label}: {str(value).strip()}"
        for label, value in items
        if value is not None and str(value).strip()
    )


def _managed_index_created_at(index_name: str, prefix: str) -> datetime | None:
    """이 색인 함수의 이름 규칙과 일치하는 물리 인덱스의 생성 시각을 반환한다."""
    if not index_name.startswith(prefix):
        return None
    suffix = index_name[len(prefix):]
    if not re.fullmatch(r"[0-9]{20}", suffix):
        return None
    try:
        return datetime.strptime(suffix, "%Y%m%d%H%M%S%f").replace(tzinfo=UTC)
    except ValueError:
        return None


def _delete_unused_managed_indices(
    es: Elasticsearch,
    *,
    alias: str,
    active_index: str,
    previous_indices: set[str],
) -> None:
    """Alias 전환 후 이전 대상과 오래된 미사용 인덱스만 정리한다."""
    prefix = f"{alias}{_MANAGED_INDEX_SUFFIX}"
    cutoff = datetime.now(UTC) - _ORPHAN_GRACE_PERIOD
    try:
        indices = es.indices.get(
            index=f"{prefix}*",
            features="aliases",
            allow_no_indices=True,
            ignore_unavailable=True,
        )
    except Exception:
        logger.exception("Failed to list unused Elasticsearch indices for %s", alias)
        return

    for index_name, metadata in indices.items():
        created_at = _managed_index_created_at(index_name, prefix)
        if index_name == active_index or created_at is None or metadata.get("aliases"):
            continue
        if index_name not in previous_indices and created_at > cutoff:
            continue
        try:
            es.indices.delete(index=index_name)
        except Exception:
            logger.exception("Failed to delete unused Elasticsearch index %s", index_name)


def reindex_postgres_to_elasticsearch(
    settings: Settings | None = None,
    *,
    client: Elasticsearch | None = None,
) -> ElasticsearchReindexResult:
    """PostgreSQL 원본 문서 전체를 Nori Elasticsearch 인덱스로 재색인한다.

    새 물리 인덱스의 Bulk 적재가 모두 성공한 뒤에만 검색 alias를 교체한다.
    따라서 실패한 재색인이 현재 검색 인덱스를 손상시키지 않는다.

    Args:
        settings: DB와 Elasticsearch 연결 설정. None이면 환경설정을 사용한다.
        client: 테스트 또는 기존 연결 재사용을 위한 선택적 Elasticsearch client.

    Returns:
        새 물리 인덱스명, alias와 적재 문서 수.

    Raises:
        ValueError: alias가 유효하지 않거나 색인할 원본 문서가 없을 때.
        Exception: Elasticsearch 연결·인덱스 생성·Bulk 적재에 실패했을 때.
    """
    resolved_settings = settings or get_settings()
    alias = resolved_settings.elasticsearch_index_alias.strip()
    if not _SAFE_INDEX_NAME.fullmatch(alias):
        raise ValueError(
            "ELASTICSEARCH_INDEX_ALIAS must contain only lowercase letters, "
            "numbers, dots, underscores, or hyphens"
        )

    documents = load_elasticsearch_source_documents(resolved_settings)
    if not documents:
        raise ValueError("No source documents are available for Elasticsearch")

    es = client or Elasticsearch(
        resolved_settings.elasticsearch_url,
        request_timeout=resolved_settings.elasticsearch_request_timeout,
    )
    # 과거 실행에서 남은 오래된 미사용 인덱스를 먼저 정리해 새 색인 공간을 확보한다.
    _delete_unused_managed_indices(
        es,
        alias=alias,
        active_index="",
        previous_indices=set(),
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    index_name = f"{alias}{_MANAGED_INDEX_SUFFIX}{timestamp}"
    created = False
    previous_indices: set[str] = set()
    try:
        es.indices.create(index=index_name, **nori_index_definition())
        created = True
        indexed_count, errors = helpers.bulk(
            es.options(request_timeout=resolved_settings.elasticsearch_request_timeout),
            iter_bulk_actions(documents, index_name),
            chunk_size=resolved_settings.elasticsearch_bulk_chunk_size,
            raise_on_error=False,
            raise_on_exception=True,
        )
        if errors:
            raise RuntimeError(
                f"Elasticsearch bulk indexing failed for {len(errors)} documents"
            )
        if indexed_count != len(documents):
            raise RuntimeError(
                f"Elasticsearch indexed {indexed_count} of {len(documents)} documents"
            )

        es.indices.refresh(index=index_name)
        alias_actions: list[dict[str, Any]] = []
        if es.indices.exists_alias(name=alias):
            current_indices = es.indices.get_alias(name=alias)
            previous_indices = set(current_indices)
            alias_actions.extend(
                {"remove": {"index": current_index, "alias": alias}}
                for current_index in current_indices.keys()
            )
        alias_actions.append({"add": {"index": index_name, "alias": alias}})
        es.indices.update_aliases(actions=alias_actions)
    except Exception:
        if created:
            try:
                active_indices = (
                    es.indices.get_alias(name=alias)
                    if es.indices.exists_alias(name=alias)
                    else {}
                )
                if index_name not in active_indices:
                    es.indices.delete(index=index_name)
            except Exception:
                logger.exception("Failed to remove incomplete Elasticsearch index %s", index_name)
        raise

    _delete_unused_managed_indices(
        es,
        alias=alias,
        active_index=index_name,
        previous_indices=previous_indices,
    )

    return {
        "index": index_name,
        "alias": alias,
        "indexed_count": indexed_count,
    }


def main() -> None:
    """명령행에서 PostgreSQL → Elasticsearch 전체 재색인을 실행한다."""
    result = reindex_postgres_to_elasticsearch()
    print(
        f"indexed={result['indexed_count']} alias={result['alias']} "
        f"index={result['index']}"
    )


if __name__ == "__main__":
    main()
