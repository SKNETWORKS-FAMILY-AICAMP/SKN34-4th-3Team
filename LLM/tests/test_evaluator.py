import asyncio
from collections import Counter
from types import SimpleNamespace

from httpx import Request, Response
import pytest

from src.evaluation.evaluator import (
    EvaluationCase,
    EvaluationObservation,
    evaluate_cases,
)
from src.evaluation.run_evaluation import (
    DEFAULT_DATASET, HttpLangGraphClient, load_evaluation_cases,
    mock_user_context, run_evaluation, validate_mock_users,
)
from src.serving.tax_calculators_docstring import calculate_tax


class FakeEvaluationClient:
    def __init__(self, observations: dict[int, EvaluationObservation]) -> None:
        self.observations = observations

    async def recommend(
        self,
        *,
        user_id: int,
        question: str,
        top_k: int,
    ) -> EvaluationObservation:
        del question, top_k
        return self.observations[user_id]


class FakeHttpClient:
    def __init__(self, response_body: dict[str, object]) -> None:
        self.response_body = response_body
        self.request_path = ""
        self.request_json: dict[str, object] = {}

    async def post(self, path: str, *, json: dict[str, object] | None = None) -> Response:
        self.request_path = path
        self.request_json = json or {}
        return Response(
            200,
            json=self.response_body,
            request=Request("POST", f"http://test{path}"),
        )


def test_http_client_evaluates_langgraph_answer_endpoint() -> None:
    client = HttpLangGraphClient("http://test")
    fake_http_client = FakeHttpClient(
        {
            "sources": [
                {"policy_id": 103},
                {"policy_id": None},
                {"policy_id": 101},
            ],
            "guardrail_reason": None,
        }
    )
    client._client = fake_http_client  # type: ignore[assignment]

    observation = asyncio.run(
        client.recommend(user_id=3, question="지원 정책을 알려줘", top_k=5)
    )

    assert fake_http_client.request_path == "/internal/rag/answer"
    assert fake_http_client.request_json == {
        "user_id": 3,
        "question": "지원 정책을 알려줘",
        "top_k": 5,
    }
    assert observation.predicted_policy_ids == [103, 101]
    assert observation.guardrail_reason is None


def test_policy_evaluation_sends_mock_profile_to_override_db_lookup() -> None:
    client = HttpLangGraphClient("http://test", user_context_provider=mock_user_context)
    fake_http_client = FakeHttpClient({"sources": [], "guardrail_reason": None})
    client._client = fake_http_client  # type: ignore[assignment]

    asyncio.run(client.recommend(user_id=4, question="지원 정책", top_k=5))

    assert fake_http_client.request_json["user_context"]["userId"] == 4
    assert fake_http_client.request_json["user_context"]["region"] is None
    validate_mock_users({1, 2, 4})


def test_evaluator_aggregates_retrieval_and_guardrail_metrics() -> None:
    cases = [
        EvaluationCase(
            case_id="retrieval",
            user_id=1,
            question="지원정책",
            relevant_policy_ids=[101, 102],
            should_block=False,
        ),
        EvaluationCase(
            case_id="blocked",
            user_id=2,
            question="날씨",
            relevant_policy_ids=[],
            should_block=True,
        ),
    ]
    client = FakeEvaluationClient(
        {
            1: EvaluationObservation(
                predicted_policy_ids=[101, 999, 102],
                guardrail_reason=None,
                latency_ms=10,
            ),
            2: EvaluationObservation(
                predicted_policy_ids=[],
                guardrail_reason="out_of_scope",
                latency_ms=20,
            ),
        }
    )

    report = asyncio.run(evaluate_cases(cases, client, k=3))

    assert report.summary.evaluated_cases == 2
    assert report.summary.retrieval_cases == 1
    assert report.summary.precision_at_k == pytest.approx(2 / 3)
    assert report.summary.recall_at_k == pytest.approx(1.0)
    assert report.summary.mrr == pytest.approx(1.0)
    assert report.summary.map == pytest.approx((1.0 + 2 / 3) / 2)
    assert report.summary.retrieval_attempted_cases == 1
    assert report.summary.conditional_precision_at_k == pytest.approx(2 / 3)
    assert report.summary.conditional_recall_at_k == pytest.approx(1.0)
    assert report.summary.failure_reasons["out_of_scope"] == 1
    assert report.summary.average_latency_ms == pytest.approx(15)
    assert report.summary.guardrail.accuracy == pytest.approx(1.0)
    assert report.cases[1].retrieval is None


def test_sample_dataset_matches_evaluation_contract() -> None:
    cases = load_evaluation_cases(DEFAULT_DATASET, mode="policy")

    assert len(cases) == 40
    assert sum(not case.should_block for case in cases) == 20
    assert sum(case.should_block for case in cases) == 20
    assert {case.user_id for case in cases} == {1, 2, 4}
    assert all(case.relevant_policy_ids for case in cases if not case.should_block)
    assert all(not case.relevant_policy_ids for case in cases if case.should_block)
    assert all(
        policy_id > 0
        for case in cases
        for policy_id in case.relevant_policy_ids
    )


def test_graph_dataset_matches_scenario_contract() -> None:
    scenarios = load_evaluation_cases(DEFAULT_DATASET, mode="graph")
    assert len(scenarios) == 20
    assert sum(len(scenario.turns) for scenario in scenarios) == 40
    assert {scenario.category for scenario in scenarios} == {"tax", "roadmap"}
    assert all(len(scenario.turns) >= 2 for scenario in scenarios)


def test_holdout250_loads_with_expected_contract_and_distribution() -> None:
    cases = load_evaluation_cases(DEFAULT_DATASET, mode="policy", suite="holdout250")
    scenarios = load_evaluation_cases(DEFAULT_DATASET, mode="graph", suite="holdout250")

    assert len(cases) == 126
    assert sum(not case.should_block for case in cases) == 63
    assert sum(case.should_block for case in cases) == 63
    assert len(scenarios) == 62
    assert all(len(scenario.turns) == 2 for scenario in scenarios)
    assert sum(len(scenario.turns) for scenario in scenarios) == 124
    assert len({policy_id for case in cases for policy_id in case.relevant_policy_ids}) == 63

    user_totals = Counter(case.user_id for case in cases)
    for scenario in scenarios:
        user_totals[scenario.user_id] += len(scenario.turns)
    assert user_totals == Counter({1: 84, 2: 84, 4: 82})
    assert all(case.tags for case in cases)
    assert all(scenario.tags for scenario in scenarios)
    assert sum(
        turn.reference is not None
        for scenario in scenarios
        for turn in scenario.turns
    ) == 10


def test_holdout250_rejects_mock_users_before_http_calls() -> None:
    arguments = SimpleNamespace(
        suite="holdout250", user_source="mock", validate_only=False,
    )

    with pytest.raises(ValueError, match="requires --user-source db"):
        asyncio.run(run_evaluation(arguments))  # type: ignore[arg-type]


def test_holdout250_tax_references_match_deterministic_calculator() -> None:
    scenarios = load_evaluation_cases(DEFAULT_DATASET, mode="graph", suite="holdout250")
    references = [
        turn.reference
        for scenario in scenarios
        for turn in scenario.turns
        if turn.reference is not None
    ]

    assert len(references) == 10
    for reference in references:
        observed = calculate_tax(
            reference["calculation_type"], **reference["inputs"],
        )
        assert all(
            observed[key] == value
            for key, value in reference["expected_result"].items()
        )



def test_insufficient_evidence_is_separate_from_input_guardrail_block() -> None:
    cases = [
        EvaluationCase(
            case_id="missed-relevant-policy",
            user_id=1,
            question="지원정책",
            relevant_policy_ids=[101],
            should_block=False,
        )
    ]
    client = FakeEvaluationClient(
        {
            1: EvaluationObservation(
                predicted_policy_ids=[],
                guardrail_reason="insufficient_evidence",
                latency_ms=10,
            )
        }
    )

    report = asyncio.run(evaluate_cases(cases, client, k=5))

    assert report.cases[0].blocked is False
    assert report.summary.guardrail.true_negative == 1
    assert report.summary.failure_reasons["insufficient_evidence"] == 1
    assert report.summary.retrieval_attempted_cases == 1
