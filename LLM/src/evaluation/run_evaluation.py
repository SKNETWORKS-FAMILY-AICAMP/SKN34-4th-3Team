import argparse
import asyncio
from collections.abc import Callable
import hashlib
import importlib.util
import json
from pathlib import Path
from time import perf_counter

from httpx import AsyncClient
from pydantic import TypeAdapter
from src.core.config import Settings, get_settings
from src.core.database import connect_database
from src.data.mock_repository import MockDataNotFoundError, get_user_profile as get_mock_user_profile
from src.data.postgres_repository import DatabaseDataNotFoundError, get_user_profile, load_policies

from src.evaluation.evaluator import (
    EvaluationCase,
    EvaluationObservation,
    evaluate_cases,
)
from src.evaluation.graph_evaluator import (
    AnswerObservation,
    ConversationScenario,
    evaluate_scenarios,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_DIR / "evaluation/evaluation_cases.py"
DEFAULT_OUTPUT = PROJECT_DIR / "evaluation/results/latest_report.json"


class HttpLangGraphClient:
    """실제 LangGraph 실행 API를 평가기에 연결하는 HTTP adapter."""

    def __init__(
        self, base_url: str, *, timeout_seconds: float = 60.0,
        user_context_provider: Callable[[int], dict[str, object]] | None = None,
    ) -> None:
        """평가용 비동기 HTTP Client를 초기화한다.

        Args:
            base_url: 실행 중인 LLM FastAPI 서버의 기본 URL.
            timeout_seconds: 평가 요청 한 건의 최대 대기 시간.
        """
        self._client = AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
        )
        self._user_context_provider = user_context_provider

    async def __aenter__(self) -> "HttpLangGraphClient":
        """async with 문에서 현재 Client를 반환한다."""
        return self

    async def __aexit__(self, *_args: object) -> None:
        """async with 문을 종료할 때 HTTP 연결을 닫는다."""
        await self._client.aclose()

    async def prepare_index(self) -> None:
        """평가 전에 서버 프로세스의 RAG 인덱스를 준비한다."""
        index_response = await self._client.post("/internal/rag/index")
        index_response.raise_for_status()

    async def recommend(
        self,
        *,
        user_id: int,
        question: str,
        top_k: int,
    ) -> EvaluationObservation:
        """정책 추천 API 응답을 평가에 필요한 관찰값으로 변환한다.

        Args:
            user_id: 평가 질문에 사용할 사용자 식별자.
            question: 검색·Guardrail을 평가할 사용자 질문.
            top_k: 정책 검색에 사용할 최대 결과 개수.

        Returns:
            예측 정책 순위, Guardrail 사유와 응답 시간을 담은 관찰값.
        """
        request_body: dict[str, object] = {
            "user_id": user_id, "question": question, "top_k": top_k,
        }
        if self._user_context_provider is not None:
            request_body["user_context"] = self._user_context_provider(user_id)
        request_started_at = perf_counter()
        graph_response = await self._client.post(
            "/internal/rag/answer",
            json=request_body,
        )
        response_latency_ms = (perf_counter() - request_started_at) * 1000
        graph_response.raise_for_status()
        response_body = graph_response.json()
        return EvaluationObservation(
            predicted_policy_ids=[
                int(source["policy_id"])
                for source in response_body.get("sources", [])
                if source.get("policy_id") is not None
            ],
            guardrail_reason=response_body.get("guardrail_reason"),
            latency_ms=response_latency_ms,
        )


class HttpChatClient:
    """Observe the public chat contract for graph scenario evaluation.

    Chat sources have no stable IDs and the response has no structured tax result;
    those observation fields remain None until the serving contract exposes them.
    """

    def __init__(
        self, base_url: str, *, timeout_seconds: float = 60.0,
        user_context_provider: Callable[[int], dict[str, object]] | None = None,
    ) -> None:
        self._client = AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_seconds)
        self._user_context_provider = user_context_provider or database_user_context
        self._user_context_cache: dict[int, dict[str, object]] = {}

    async def __aenter__(self) -> "HttpChatClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self._client.aclose()

    async def answer(
        self, *, user_id: int, category: str, question: str,
        history: list[dict[str, str]], roadmap_step: str | None,
    ) -> AnswerObservation:
        if user_id not in self._user_context_cache:
            self._user_context_cache[user_id] = self._user_context_provider(user_id)
        body: dict[str, object] = {
            "category": category,
            "question": question,
            "userContext": self._user_context_cache[user_id],
            "conversationHistory": history,
        }
        if roadmap_step is not None:
            body["roadmapStep"] = roadmap_step
        started_at = perf_counter()
        response = await self._client.post("/rag/chat", json=body)
        latency_ms = (perf_counter() - started_at) * 1000
        response.raise_for_status()
        result = response.json()
        return AnswerObservation(
            route=result["route"], status=result["status"],
            answer=result["answer"], grounded=result["grounded"],
            guardrail_reason=result.get("guardrail_reason"),
            latency_ms=latency_ms,
        )


def database_user_context(user_id: int, settings: Settings | None = None) -> dict[str, object]:
    """Read the real user and business profile, then map it to /rag/chat."""
    profile = get_user_profile(user_id, settings or get_settings())
    return _chat_user_context(profile)


def mock_user_context(user_id: int) -> dict[str, object]:
    """Read a fixture user profile and map it to the serving contract."""
    return _chat_user_context(get_mock_user_profile(user_id))


def _chat_user_context(profile: dict[str, object]) -> dict[str, object]:
    business = profile["business"]
    return {
        "userId": profile["user_id"],
        "age": profile["age"],
        "region": profile["region"],
        "businessType": business["business_type"],
        "industry": business["industry"],
        "businessRegisteredAt": business.get("business_registered_at"),
        "foundedAt": business["founded_at"],
    }


def validate_database_users(user_ids: set[int], settings: Settings | None = None) -> None:
    """Fail before API/model calls if any evaluation user lacks a DB profile."""
    resolved_settings = settings or get_settings()
    if resolved_settings.vector_store_backend != "postgres":
        raise ValueError("DB evaluation requires vector_store_backend=postgres")
    for user_id in sorted(user_ids):
        try:
            get_user_profile(user_id, resolved_settings)
        except DatabaseDataNotFoundError as exc:
            raise ValueError(f"Evaluation user {user_id} has no DB profile") from exc


def validate_mock_users(user_ids: set[int]) -> None:
    """Fail before API calls if a fixture user is missing."""
    for user_id in sorted(user_ids):
        try:
            get_mock_user_profile(user_id)
        except MockDataNotFoundError as exc:
            raise ValueError(f"Evaluation user {user_id} has no mock profile") from exc


def validate_users(user_ids: set[int], source: str) -> None:
    if source == "mock":
        validate_mock_users(user_ids)
    elif source == "db":
        validate_database_users(user_ids)
    else:
        raise ValueError(f"Unknown user source: {source}")


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_holdout_database(settings: Settings | None = None) -> dict[str, object]:
    """현재 DB가 holdout250을 만든 고정 snapshot과 일치하는지 읽기 전용 검증한다."""
    from evaluation.holdout_cases_250 import (
        POLICY_SOURCE_FINGERPRINT,
        SELECTED_POLICY_IDS,
        USER_PROFILE_FINGERPRINT,
        USER_PROFILE_SNAPSHOT,
    )

    resolved_settings = settings or get_settings()
    validate_database_users(set(USER_PROFILE_SNAPSHOT), resolved_settings)
    profiles = [
        get_user_profile(user_id, resolved_settings)
        for user_id in sorted(USER_PROFILE_SNAPSHOT)
    ]
    profile_fingerprint = _fingerprint(profiles)
    if profile_fingerprint != USER_PROFILE_FINGERPRINT:
        raise ValueError(
            "holdout250 DB user profile fingerprint mismatch: "
            f"expected={USER_PROFILE_FINGERPRINT}, actual={profile_fingerprint}"
        )

    selected_ids = set(SELECTED_POLICY_IDS)
    selected_policies = [
        policy for policy in load_policies(resolved_settings)
        if policy["id"] in selected_ids
    ]
    found_ids = {policy["id"] for policy in selected_policies}
    missing_policy_ids = sorted(selected_ids - found_ids)
    if missing_policy_ids:
        raise ValueError(f"holdout250 policies missing from DB: {missing_policy_ids}")
    policy_fingerprint = _fingerprint(selected_policies)
    if policy_fingerprint != POLICY_SOURCE_FINGERPRINT:
        raise ValueError(
            "holdout250 policy fingerprint mismatch: "
            f"expected={POLICY_SOURCE_FINGERPRINT}, actual={policy_fingerprint}"
        )

    with connect_database(resolved_settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(
                """
                SELECT DISTINCT source_id
                FROM rag_documents
                WHERE source_type = 'policy' AND source_id = ANY(%s)
                """,
                (sorted(selected_ids),),
            )
            chunk_policy_ids = {int(row[0]) for row in cursor.fetchall()}
    missing_chunk_ids = sorted(selected_ids - chunk_policy_ids)
    if missing_chunk_ids:
        raise ValueError(
            f"holdout250 policies missing rag_documents chunks: {missing_chunk_ids}"
        )
    return {
        "users": len(profiles),
        "policies": len(selected_policies),
        "policy_ids_with_chunks": len(chunk_policy_ids),
        "user_profile_fingerprint": profile_fingerprint,
        "policy_source_fingerprint": policy_fingerprint,
    }


def build_parser() -> argparse.ArgumentParser:
    """검색·Guardrail 평가 CLI argument parser를 생성한다.

    Returns:
        평가셋, 출력 경로, API URL, k와 인덱스 준비 옵션이 등록된 parser.
    """
    argument_parser = argparse.ArgumentParser(
        description="Evaluate policy retrieval and scope guardrails."
    )
    argument_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    argument_parser.add_argument("--mode", choices=("policy", "graph"), default="policy")
    argument_parser.add_argument(
        "--suite", choices=("legacy80", "holdout250"), default="legacy80",
    )
    argument_parser.add_argument("--user-source", choices=("mock", "db"), default="mock")
    argument_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    argument_parser.add_argument("--base-url", default="http://localhost:8001")
    argument_parser.add_argument("--k", type=int, default=5)
    argument_parser.add_argument(
        "--prepare-index",
        action="store_true",
        help="Load the local vector cache before evaluation",
    )
    argument_parser.add_argument(
        "--validate-only", action="store_true",
        help="Validate dataset and DB fingerprints without any HTTP or model call",
    )
    return argument_parser


async def run_evaluation(cli_arguments: argparse.Namespace) -> None:
    """평가셋으로 RAG API를 실행하고 JSON 보고서를 저장한다.

    Args:
        cli_arguments: CLI에서 받은 평가셋·출력 경로·API URL·k 설정.

    Notes:
        실제 API를 대상으로 실행하면 Query Embedding과 LLM 비용이 발생할 수 있다.
    """
    suite = cli_arguments.suite
    if suite == "holdout250" and cli_arguments.user_source != "db":
        raise ValueError("holdout250 requires --user-source db")

    if cli_arguments.validate_only:
        policy_cases = load_evaluation_cases(
            cli_arguments.dataset, mode="policy", suite=suite,
        )
        graph_scenarios = load_evaluation_cases(
            cli_arguments.dataset, mode="graph", suite=suite,
        )
        user_ids = {item.user_id for item in policy_cases + graph_scenarios}
        validate_users(user_ids, cli_arguments.user_source)
        validation: dict[str, object] = {
            "suite": suite,
            "policy_guardrail_cases": len(policy_cases),
            "graph_scenarios": len(graph_scenarios),
            "graph_turns": sum(len(item.turns) for item in graph_scenarios),
        }
        if suite == "holdout250":
            validation["database"] = validate_holdout_database()
        print(json.dumps(validation, ensure_ascii=False, indent=2))
        return

    if suite == "holdout250":
        validate_holdout_database()

    if cli_arguments.mode == "graph":
        scenarios = load_evaluation_cases(
            cli_arguments.dataset, mode="graph", suite=suite,
        )
        validate_users({scenario.user_id for scenario in scenarios}, cli_arguments.user_source)
        provider = mock_user_context if cli_arguments.user_source == "mock" else database_user_context
        async with HttpChatClient(
            cli_arguments.base_url, user_context_provider=provider,
        ) as evaluation_client:
            evaluation_report = await evaluate_scenarios(scenarios, evaluation_client)
    else:
        evaluation_cases = load_evaluation_cases(
            cli_arguments.dataset, mode="policy", suite=suite,
        )
        validate_users({case.user_id for case in evaluation_cases}, cli_arguments.user_source)
        provider = mock_user_context if cli_arguments.user_source == "mock" else None
        async with HttpLangGraphClient(
            cli_arguments.base_url, user_context_provider=provider,
        ) as evaluation_client:
            if cli_arguments.prepare_index:
                await evaluation_client.prepare_index()
            evaluation_report = await evaluate_cases(
                evaluation_cases,
                evaluation_client,
                k=cli_arguments.k,
            )

    report_json = evaluation_report.model_dump_json(indent=2)
    cli_arguments.output.parent.mkdir(parents=True, exist_ok=True)
    cli_arguments.output.write_text(report_json, encoding="utf-8")
    print(report_json)
    print(f"Saved report to: {cli_arguments.output}")


def load_evaluation_cases(
    dataset: Path, *, mode: str, suite: str = "legacy80",
) -> list[EvaluationCase] | list[ConversationScenario]:
    """Load the maintained Python dataset or an explicitly supplied JSON dataset."""
    if dataset.suffix == ".json":
        if suite != "legacy80":
            raise ValueError("--suite holdout250 requires evaluation/evaluation_cases.py")
        contents = dataset.read_text(encoding="utf-8")
        if mode == "graph":
            return TypeAdapter(list[ConversationScenario]).validate_json(contents)
        return TypeAdapter(list[EvaluationCase]).validate_json(contents)
    if dataset.resolve() != DEFAULT_DATASET.resolve():
        raise ValueError("Python evaluation dataset must be evaluation/evaluation_cases.py")
    spec = importlib.util.spec_from_file_location("evaluation_cases", dataset)
    if spec is None or spec.loader is None:
        raise ValueError(f"Cannot load evaluation dataset: {dataset}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_counts(suite)
    if mode == "graph":
        return TypeAdapter(list[ConversationScenario]).validate_python(
            module.GRAPH_SCENARIOS_BY_SUITE[suite]
        )
    return TypeAdapter(list[EvaluationCase]).validate_python(
        module.POLICY_CASES_BY_SUITE[suite]
    )


def main() -> None:
    """CLI 입력을 검증하고 비동기 평가 실행기를 시작한다."""
    cli_arguments = build_parser().parse_args()
    if cli_arguments.k < 1:
        raise SystemExit("--k must be at least 1")
    if cli_arguments.mode == "graph" and cli_arguments.prepare_index:
        raise SystemExit("--prepare-index is only supported in policy mode")
    try:
        asyncio.run(run_evaluation(cli_arguments))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Evaluation failed: {exc}") from exc


if __name__ == "__main__":
    main()
