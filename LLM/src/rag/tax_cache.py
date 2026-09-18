"""Persistent cache for tax retrieval evidence and reusable evidence decisions."""

import hashlib
import json
import re
from datetime import datetime, timedelta

from langchain_core.embeddings import Embeddings
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from src.core.config import Settings
from src.core.database import connect_database
from src.data.contracts import UserProfile, VectorSearchResult
from src.vectorstores.postgres import PostgresVectorSearch


_REGIONS = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
_INDUSTRIES = (
    "음식점", "제조업", "도소매", "소매업", "도매업", "숙박업",
    "부동산업", "서비스업", "소프트웨어", "정보통신업", "건설업",
)
_EVIDENCE_DECISION_CACHE_VERSION = "tax-evidence-v1"
_DECISION_SIGNATURE_VERSION = "tax-decision-facts-v1"
_EMBEDDING_VERSION = "topic-v3"
_NEGATIVE_EVIDENCE_TTL = timedelta(hours=6)


def _normalized_question(question: str) -> str:
    return " ".join(question.casefold().split())


def _user_conditions(question: str, profile: UserProfile | None) -> dict[str, object]:
    """Use only tax-relevant profile fields and explicit high-impact question facts."""
    profile_values = profile or {}
    business = profile_values.get("business") or {}
    normalized = _normalized_question(question)
    age = profile_values.get("age")
    conditions: dict[str, object] = {
        "age": age if isinstance(age, int) and not isinstance(age, bool) else None,
        "region": (profile_values.get("region") or "").strip().casefold() or None,
        "industry": (business.get("industry") or "").strip().casefold() or None,
        "founded_at": (business.get("founded_at") or "").strip() or None,
        "question_numbers": sorted(set(re.findall(r"\d+(?:[.,]\d+)?", normalized))),
        "question_regions": sorted(region for region in _REGIONS if region in normalized),
        "question_industries": sorted(industry for industry in _INDUSTRIES if industry in normalized),
        "question_youth": (
            "비청년" if "비청년" in normalized or re.search(
                r"청년(?:이|은|이/가)?\s*(?:아닌|아니|아님|해당\s*안)", normalized
            ) else "청년" if "청년" in normalized else None
        ),
        "question_startup": (
            "restartup" if "재창업" in normalized or "재 창업" in normalized
            or "폐업 후 다시" in normalized
            else "first" if any(term in normalized for term in (
                "최초 창업", "최초창업", "첫 창업", "처음 창업"
            ))
            else "new" if "신규 창업" in normalized or "신규창업" in normalized
            else None
        ),
    }
    return conditions


def _decision_scope(question: str) -> str:
    """Map phrasing variants to a conservative tax intent and requested facet."""
    normalized = _normalized_question(question)
    compact = re.sub(r"\s+", "", normalized)
    if "청년" in compact and "창업" in compact:
        topic = "youth_startup_reduction"
    elif "창업" in compact and any(
        keyword in compact for keyword in ("감면", "세액", "조세특례")
    ):
        topic = "startup_reduction"
    elif any(keyword in compact for keyword in ("원천징수", "월급", "급여")):
        topic = "withholding_tax"
    elif any(keyword in compact for keyword in ("부가가치세", "부가세", "매입세액")):
        topic = "vat"
    elif any(keyword in compact for keyword in ("종합소득세", "소득세")):
        topic = "income_tax"
    elif any(keyword in compact for keyword in ("필요경비", "경비처리", "공제")):
        topic = "expense_deduction"
    else:
        topic = "tax_general"

    if any(keyword in compact for keyword in ("대상", "해당", "자격")):
        facet = "eligibility"
    elif any(keyword in compact for keyword in ("연령", "나이", "생년")):
        facet = "age"
    elif "업종" in compact:
        facet = "industry"
    elif any(keyword in compact for keyword in ("지역", "수도권", "과밀억제")):
        facet = "region"
    elif any(keyword in compact for keyword in ("감면율", "세율", "비율")):
        facet = "rate"
    elif any(keyword in compact for keyword in ("기간", "언제까지", "몇년")):
        facet = "period"
    elif any(keyword in compact for keyword in ("계산", "얼마")):
        facet = "calculation"
    else:
        facet = "general"
    return f"{topic}:{facet}"


def _decision_conditions(
    question: str, profile: UserProfile | None
) -> dict[str, object]:
    """Collapse repeated profile/question facts into one stable condition set."""
    raw = _user_conditions(question, profile)
    profile_values = profile or {}
    business = profile_values.get("business") or {}

    regions = set(raw["question_regions"])
    profile_region = raw["region"]
    if isinstance(profile_region, str):
        matched = {region for region in _REGIONS if region.casefold() in profile_region}
        regions.update(matched or {profile_region})

    industries = set(raw["question_industries"])
    profile_industry = raw["industry"]
    if isinstance(profile_industry, str):
        matched = {
            industry for industry in _INDUSTRIES
            if industry.casefold() in profile_industry
        }
        industries.update(matched or {profile_industry})

    represented_numbers: set[str] = set()
    age = raw["age"]
    if isinstance(age, int):
        represented_numbers.add(str(age))
    founded_at = raw["founded_at"]
    if isinstance(founded_at, str):
        for part in re.findall(r"\d+", founded_at):
            represented_numbers.update({part, part.lstrip("0") or "0"})

    return {
        "age": age,
        "regions": sorted(regions),
        "industries": sorted(industries),
        "business_type": (
            (business.get("business_type") or "").strip().casefold() or None
        ),
        "founded_at": founded_at,
        "question_numbers": sorted(
            number for number in raw["question_numbers"]
            if number not in represented_numbers
        ),
        "question_youth": raw["question_youth"],
        "question_startup": raw["question_startup"],
    }


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class TaxRagCache:
    def __init__(
        self, settings: Settings, embedding: Embeddings, vector_search: PostgresVectorSearch
    ) -> None:
        self._settings = settings
        self._embedding = embedding
        self._vector_search = vector_search

    def lookup(
        self,
        question: str,
        profile: UserProfile | None,
        prior_evidence_ids: list[int] | None = None,
    ) -> tuple[
        list[VectorSearchResult], list[str], list[float] | None,
        dict[str, object] | None, str | None,
    ]:
        """Reuse decisions strictly, while allowing broader retrieval-only hits."""
        question = _normalized_question(question)
        conditions = _user_conditions(question, profile)
        decision_conditions = _decision_conditions(question, profile)
        prior_ids = sorted(prior_evidence_ids or [])
        key = self._decision_lookup_key(question, decision_conditions, prior_ids)
        with connect_database(self._settings) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "SELECT cached_result, created_at FROM tax_rag_cache WHERE cache_key = %s",
                    (key,),
                )
                exact = cursor.fetchone()
                if exact is None:
                    legacy_key = self._key(question, conditions, prior_ids)
                    cursor.execute(
                        "SELECT cached_result, created_at FROM tax_rag_cache "
                        "WHERE cache_key = %s",
                        (legacy_key,),
                    )
                    exact = cursor.fetchone()
        if exact is not None:
            restored = self._restore(
                exact["cached_result"], conditions, decision_conditions,
                exact["created_at"], prior_ids,
            )
            if restored is not None:
                documents, queries, decision = restored
                if not self._valid_decision_signature(
                    exact["cached_result"], question, decision_conditions, prior_ids
                ):
                    embedding = self._embedding.embed_query(
                        self._embedding_text(question)
                    )
                    documents = self._restore_retrieval(
                        exact["cached_result"], exact["created_at"]
                    )
                    if documents:
                        return documents, [question], embedding, None, "retrieval"
                return documents, queries, None, decision, (
                    "decision" if decision is not None else "full"
                )

        embedding = self._embedding.embed_query(self._embedding_text(question))
        with connect_database(self._settings) as connection:
            register_vector(connection)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT cached_result, created_at,
                           1 - (question_embedding <=> %s) AS similarity
                    FROM tax_rag_cache
                    WHERE question_embedding IS NOT NULL
                    ORDER BY question_embedding <=> %s
                    LIMIT 5
                    """,
                    (Vector(embedding), Vector(embedding)),
                )
                candidates = cursor.fetchall()
        for candidate in candidates:
            similarity = candidate["similarity"]
            if similarity is None or float(similarity) < self._settings.tax_cache_similarity_threshold:
                break
            if (
                isinstance(candidate["cached_result"], dict)
                and candidate["cached_result"].get("embedding_version")
                == _EMBEDDING_VERSION
                and self._valid_decision_signature(
                    candidate["cached_result"], question,
                    decision_conditions, prior_ids,
                )
                and float(similarity)
                >= self._settings.tax_cache_decision_similarity_threshold
            ):
                restored = self._restore(
                    candidate["cached_result"], conditions, decision_conditions,
                    candidate["created_at"], prior_ids,
                )
                if restored is not None:
                    documents, queries, decision = restored
                    return documents, queries, embedding, decision, (
                        "decision" if decision is not None else "full"
                    )
            documents = self._restore_retrieval(
                candidate["cached_result"], candidate["created_at"]
            )
            if documents:
                return documents, [question], embedding, None, "retrieval"
        return [], [], embedding, None, None

    def save(
        self,
        question: str,
        profile: UserProfile | None,
        documents: list[VectorSearchResult],
        hop_queries: list[str],
        embedding: list[float] | None,
        *,
        evidence_decision: dict[str, object] | None = None,
        prior_evidence_ids: list[int] | None = None,
    ) -> None:
        ids = [document.get("id") for document in documents]
        if (
            not ids or not hop_queries
            or any(not isinstance(document_id, int) or isinstance(document_id, bool)
                   for document_id in ids)
        ):
            return
        question = _normalized_question(question)
        conditions = _user_conditions(question, profile)
        decision_conditions = _decision_conditions(question, profile)
        prior_ids = sorted(prior_evidence_ids or [])
        if embedding is None:
            embedding = self._embedding.embed_query(self._embedding_text(question))
        prior_id_set = set(prior_ids)
        result = {
            "hop_queries": hop_queries,
            "embedding_ids": ids,
            "retrieval_ids": [value for value in ids if value not in prior_id_set],
            "embedding_version": _EMBEDDING_VERSION,
            "decision_question": question,
            "decision_scope": _decision_scope(question),
            "decision_conditions": decision_conditions,
            "decision_lookup_key": self._decision_lookup_key(
                question, decision_conditions, prior_ids
            ),
            "decision_signature": self._decision_signature(
                question, decision_conditions, prior_ids, ids
            ),
            "user_conditions": conditions,
        }
        if evidence_decision is not None:
            result.update({
                "evidence_cache_version": _EVIDENCE_DECISION_CACHE_VERSION,
                "llm_model": self._settings.llm_model,
                "prior_evidence_ids": prior_ids,
                "evidence_decision": evidence_decision,
            })
        with connect_database(self._settings) as connection:
            register_vector(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tax_rag_cache
                        (cache_key, question, question_embedding, cached_result)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (cache_key) DO UPDATE SET
                        question = EXCLUDED.question,
                        question_embedding = EXCLUDED.question_embedding,
                        cached_result = EXCLUDED.cached_result,
                        created_at = now()
                    """,
                    (
                        self._decision_lookup_key(
                            question, decision_conditions, prior_ids
                        ),
                        question,
                        Vector(embedding), json.dumps(result, ensure_ascii=False),
                    ),
                )

    def _restore(
        self,
        result: object,
        conditions: dict[str, object],
        decision_conditions: dict[str, object],
        created_at: datetime,
        prior_evidence_ids: list[int],
    ) -> tuple[
        list[VectorSearchResult], list[str], dict[str, object] | None
    ] | None:
        if not isinstance(result, dict):
            return None
        if (
            result.get("user_conditions") != conditions
            and result.get("decision_conditions") != decision_conditions
        ):
            return None
        ids = result.get("embedding_ids")
        queries = result.get("hop_queries")
        decision = result.get("evidence_decision")
        if (
            not isinstance(ids, list) or not ids
            or any(not isinstance(value, int) or isinstance(value, bool) for value in ids)
            or len(set(ids)) != len(ids)
            or not isinstance(queries, list) or not queries
            or any(not isinstance(query, str) for query in queries)
        ):
            return None
        if decision is not None:
            if (
                not isinstance(decision, dict)
                or result.get("evidence_cache_version") != _EVIDENCE_DECISION_CACHE_VERSION
                or result.get("llm_model") != self._settings.llm_model
                or result.get("prior_evidence_ids", []) != prior_evidence_ids
            ):
                return None
            if decision.get("sufficient") is False:
                now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
                if now - created_at > _NEGATIVE_EVIDENCE_TTL:
                    return None
        elif prior_evidence_ids:
            return None
        documents = self._vector_search.get_tax_evidence_by_ids(ids, created_at)
        return (documents, queries, decision) if len(documents) == len(ids) else None

    @staticmethod
    def _decision_lookup_key(
        question: str,
        conditions: dict[str, object],
        prior_evidence_ids: list[int],
    ) -> str:
        return _digest([
            _DECISION_SIGNATURE_VERSION,
            _decision_scope(question),
            conditions,
            {"prior_evidence_ids": sorted(prior_evidence_ids)},
        ])

    @staticmethod
    def _decision_signature(
        question: str,
        conditions: dict[str, object],
        prior_evidence_ids: list[int],
        evidence_ids: list[object],
    ) -> str:
        return _digest([
            _DECISION_SIGNATURE_VERSION,
            _decision_scope(question),
            conditions,
            {"prior_evidence_ids": sorted(prior_evidence_ids)},
            {"evidence_ids": sorted(evidence_ids)},
        ])

    def _valid_decision_signature(
        self,
        result: object,
        question: str,
        conditions: dict[str, object],
        prior_evidence_ids: list[int],
    ) -> bool:
        if not isinstance(result, dict):
            return False
        ids = result.get("embedding_ids")
        return (
            isinstance(ids, list)
            and bool(ids)
            and all(isinstance(value, int) and not isinstance(value, bool) for value in ids)
            and result.get("decision_signature")
            == self._decision_signature(
                question, conditions, prior_evidence_ids, ids
            )
        )

    def _restore_retrieval(
        self, result: object, created_at: datetime
    ) -> list[VectorSearchResult]:
        if not isinstance(result, dict):
            return []
        ids = result.get("retrieval_ids")
        if ids is None:
            stored_prior_ids = result.get("prior_evidence_ids", [])
            if not isinstance(stored_prior_ids, list):
                return []
            prior_ids = set(stored_prior_ids)
            ids = [
                value for value in result.get("embedding_ids", [])
                if value not in prior_ids
            ]
        if (
            not isinstance(ids, list) or not ids
            or any(not isinstance(value, int) or isinstance(value, bool) for value in ids)
            or len(set(ids)) != len(ids)
        ):
            return []
        documents = self._vector_search.get_tax_evidence_by_ids(ids, created_at)
        return documents if len(documents) == len(ids) else []

    @staticmethod
    def _key(
        question: str,
        conditions: dict[str, object],
        prior_evidence_ids: list[int] | None = None,
    ) -> str:
        payload: list[object] = [question, conditions]
        if prior_evidence_ids:
            payload.append({"prior_evidence_ids": sorted(prior_evidence_ids)})
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _embedding_text(
        question: str,
    ) -> str:
        compact = re.sub(r"\s+", "", question)
        if (
            "청년" in compact
            and "창업" in compact
            and any(keyword in compact for keyword in ("감면", "세액", "조세특례"))
        ):
            return "청년 창업 세액감면 대상 요건"
        return question
