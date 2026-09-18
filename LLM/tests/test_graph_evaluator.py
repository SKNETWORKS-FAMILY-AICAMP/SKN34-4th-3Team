import asyncio
from decimal import Decimal

import pytest

from src.evaluation.graph_evaluator import (
    AnswerExpectation, AnswerObservation, ConversationScenario,
    ConversationTurn, evaluate_scenarios, score_answer,
)
from src.evaluation.run_evaluation import HttpChatClient, database_user_context, validate_database_users
from httpx import Request, Response


def observation(**changes: object) -> AnswerObservation:
    values = dict(route="tax", status="success", answer="세액 100원", source_ids={"tax:1"},
                  grounded=True, calculation_type="income_tax", calculation_result={"tax": "100"},
                  latency_ms=10)
    values.update(changes)
    return AnswerObservation.model_validate(values)


def test_scores_route_evidence_answer_and_numeric_result() -> None:
    expected = AnswerExpectation(
        route="tax", status="success", required_source_ids={"tax:1"},
        required_phrases=["세액"], forbidden_phrases=["추측"], require_grounded=True,
        calculation_type="income_tax", calculation_values={"tax": Decimal("101")},
        numeric_tolerance=Decimal("1"),
    )
    assert score_answer(expected, observation()).passed
    score = score_answer(expected, observation(source_ids=None, calculation_result={"tax": "99"}))
    assert score.checks["sources"] is False
    assert score.checks["calculation_values"] is False


def test_missing_observation_does_not_pass_and_empty_rubric_is_invalid() -> None:
    assert not score_answer(
        AnswerExpectation(calculation_type="income_tax", calculation_values={"tax": Decimal(100)}),
        observation(calculation_result={"tax": True}),
    ).passed
    with pytest.raises(ValueError, match="at least one"):
        score_answer(AnswerExpectation(), observation())


def test_non_scope_failures_are_not_counted_as_input_blocks() -> None:
    score = score_answer(
        AnswerExpectation(should_block=False),
        observation(
            status="insufficient_evidence",
            guardrail_reason="insufficient_evidence",
        ),
    )

    assert score.checks["block"] is True
    assert score.guardrail_reason == "insufficient_evidence"


class RecordingClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str, list[dict[str, str]]]] = []

    async def answer(self, *, user_id: int, category: str, question: str,
                     history: list[dict[str, str]], roadmap_step: str | None) -> AnswerObservation:
        self.calls.append((user_id, category, history))
        return observation(route="roadmap", answer=f"답변: {question}", calculation_type=None,
                           calculation_result=None, source_ids=None, grounded=False)


def test_multiturn_history_and_scenario_isolation() -> None:
    client = RecordingClient()
    scenarios = [
        ConversationScenario(
            scenario_id=str(user_id), user_id=user_id,
            category="roadmap" if user_id == 1 else "tax",
            turns=[
                ConversationTurn(question="첫 질문", expected=AnswerExpectation(route="roadmap")),
                ConversationTurn(question="후속 질문", expected=AnswerExpectation(route="roadmap")),
            ],
        ) for user_id in (1, 2)
    ]
    report = asyncio.run(evaluate_scenarios(scenarios, client))
    assert report.scenario_pass_rate == 1
    assert report.turn_pass_rate == 1
    assert client.calls[0][2] == []
    assert client.calls[1][2] == [
        {"role": "user", "content": "첫 질문"},
        {"role": "assistant", "content": "답변: 첫 질문"},
    ]
    assert client.calls[2][2] == []
    assert client.calls[2][1] == "tax"


def test_chat_adapter_sends_history_and_marks_unavailable_fields_missing() -> None:
    class FakeHttp:
        request_body: dict[str, object]

        async def post(self, path: str, *, json: dict[str, object]) -> Response:
            assert path == "/rag/chat"
            self.request_body = json
            return Response(200, request=Request("POST", "http://test/rag/chat"), json={
                "route": "roadmap", "status": "success", "answer": "다음 단계",
                "grounded": False, "sources": [], "guardrail_reason": None,
            })

    client = HttpChatClient("http://test", user_context_provider=lambda user_id: {
        "userId": user_id, "age": 30, "region": "서울",
        "businessType": "개인", "industry": "서비스",
    })
    fake = FakeHttp()
    client._client = fake  # type: ignore[assignment]
    result = asyncio.run(client.answer(
        user_id=4, category="roadmap", question="다음은?",
        history=[{"role": "user", "content": "시작"},
                 {"role": "assistant", "content": "준비"}], roadmap_step=None,
    ))
    assert fake.request_body["userContext"]["region"] == "서울"
    assert len(fake.request_body["conversationHistory"]) == 2
    assert result.source_ids is None
    assert result.calculation_result is None


def test_db_profile_maps_to_chat_context(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.evaluation.run_evaluation as runner

    calls: list[int] = []
    def profile(user_id: int, _settings: object) -> dict[str, object]:
        calls.append(user_id)
        return {"user_id": user_id, "age": 27, "region": "부산", "business": {
            "business_type": "개인", "industry": "제조", "founded_at": "2025-01-01",
        }}

    monkeypatch.setattr(runner, "get_user_profile", profile)
    context = database_user_context(7)
    assert context["userId"] == 7
    assert context["age"] == 27
    assert context["industry"] == "제조"
    settings = runner.Settings(vector_store_backend="postgres")
    validate_database_users({7, 2}, settings)
    assert calls == [7, 2, 7]
