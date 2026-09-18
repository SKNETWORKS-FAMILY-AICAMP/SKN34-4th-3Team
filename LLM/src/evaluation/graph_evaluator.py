"""Dataset-independent scoring for graph answers and completed conversations."""

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol

from pydantic import BaseModel, Field, model_validator


Route = Literal["policy", "notice", "tax", "roadmap"]
Status = Literal[
    "success", "need_more_info", "insufficient_evidence", "no_result",
    "integration_unavailable", "error",
]


class AnswerExpectation(BaseModel):
    route: Route | None = None
    status: Status | None = None
    should_block: bool | None = None
    required_source_ids: set[str] | None = None
    required_phrases: list[str] = Field(default_factory=list)
    forbidden_phrases: list[str] = Field(default_factory=list)
    require_grounded: bool | None = None
    calculation_type: str | None = None
    calculation_values: dict[str, Decimal] | None = None
    numeric_tolerance: Decimal = Decimal("0")
    max_answer_chars: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_expectation(self) -> "AnswerExpectation":
        if self.numeric_tolerance < 0:
            raise ValueError("numeric_tolerance must be nonnegative")
        if self.calculation_values is not None and self.calculation_type is None:
            raise ValueError("calculation_type is required for calculation_values")
        return self


class AnswerObservation(BaseModel):
    route: Route
    status: Status
    answer: str
    source_ids: set[str] | None = None
    grounded: bool
    guardrail_reason: str | None = None
    calculation_type: str | None = None
    calculation_result: dict[str, object] | None = None
    latency_ms: float = Field(ge=0)


class AnswerScore(BaseModel):
    checks: dict[str, bool]
    passed: bool
    latency_ms: float
    guardrail_reason: str | None


def score_answer(expected: AnswerExpectation, observed: AnswerObservation) -> AnswerScore:
    """Score only specified expectations; missing observable fields fail their checks."""
    checks: dict[str, bool] = {}
    if expected.route is not None:
        checks["route"] = observed.route == expected.route
    if expected.status is not None:
        checks["status"] = observed.status == expected.status
    if expected.should_block is not None:
        checks["block"] = (
            observed.guardrail_reason == "out_of_scope"
        ) == expected.should_block
    if expected.required_source_ids is not None:
        checks["sources"] = (
            observed.source_ids is not None
            and expected.required_source_ids <= observed.source_ids
        )
    if expected.require_grounded is not None:
        checks["grounded"] = observed.grounded == expected.require_grounded
    if expected.required_phrases:
        checks["required_phrases"] = all(
            phrase.casefold() in observed.answer.casefold()
            for phrase in expected.required_phrases
        )
    if expected.forbidden_phrases:
        checks["forbidden_phrases"] = all(
            phrase.casefold() not in observed.answer.casefold()
            for phrase in expected.forbidden_phrases
        )
    if expected.max_answer_chars is not None:
        checks["answer_length"] = len(observed.answer) <= expected.max_answer_chars
    if expected.calculation_type is not None:
        checks["calculation_type"] = observed.calculation_type == expected.calculation_type
    if expected.calculation_values is not None:
        checks["calculation_values"] = (
            observed.calculation_result is not None
            and all(
                _number_matches(observed.calculation_result.get(key), value, expected.numeric_tolerance)
                for key, value in expected.calculation_values.items()
            )
        )
    if not checks:
        raise ValueError("at least one answer expectation is required")
    return AnswerScore(
        checks=checks,
        passed=all(checks.values()),
        latency_ms=observed.latency_ms,
        guardrail_reason=observed.guardrail_reason,
    )


def _number_matches(actual: object, expected: Decimal, tolerance: Decimal) -> bool:
    if actual is None or isinstance(actual, bool):
        return False
    try:
        value = Decimal(str(actual))
    except (InvalidOperation, ValueError):
        return False
    return value.is_finite() and abs(value - expected) <= tolerance


class ConversationTurn(BaseModel):
    question: str = Field(min_length=1)
    expected: AnswerExpectation
    reference: dict[str, object] | None = None


class ConversationScenario(BaseModel):
    scenario_id: str
    user_id: int = Field(gt=0)
    category: Literal["tax", "expense", "saving", "policy", "roadmap"]
    turns: list[ConversationTurn] = Field(min_length=2)
    roadmap_step: str | None = None
    tags: list[str] = Field(default_factory=list)


class GraphEvaluationClient(Protocol):
    async def answer(
        self, *, user_id: int, category: str, question: str,
        history: list[dict[str, str]], roadmap_step: str | None,
    ) -> AnswerObservation: ...


class ScenarioResult(BaseModel):
    scenario_id: str
    turns: list[AnswerScore]
    passed: bool
    tags: list[str] = Field(default_factory=list)


class GraphEvaluationReport(BaseModel):
    scenarios: list[ScenarioResult]
    scenario_pass_rate: float
    turn_pass_rate: float
    check_pass_rates: dict[str, float]
    average_latency_ms: float
    failure_reasons: dict[str, int]


async def evaluate_scenarios(
    scenarios: Sequence[ConversationScenario], client: GraphEvaluationClient,
) -> GraphEvaluationReport:
    """Execute full turns; history is scoped to one user/category scenario."""
    results: list[ScenarioResult] = []
    scores: list[AnswerScore] = []
    for scenario in scenarios:
        history: list[dict[str, str]] = []
        turn_scores: list[AnswerScore] = []
        for turn in scenario.turns:
            observed = await client.answer(
                user_id=scenario.user_id, category=scenario.category,
                question=turn.question, history=[item.copy() for item in history],
                roadmap_step=scenario.roadmap_step,
            )
            score = score_answer(turn.expected, observed)
            turn_scores.append(score)
            scores.append(score)
            history.extend((
                {"role": "user", "content": turn.question},
                {"role": "assistant", "content": observed.answer},
            ))
        results.append(ScenarioResult(
            scenario_id=scenario.scenario_id, turns=turn_scores,
            passed=all(score.passed for score in turn_scores), tags=scenario.tags,
        ))
    names = {name for score in scores for name in score.checks}
    return GraphEvaluationReport(
        scenarios=results,
        scenario_pass_rate=_rate([result.passed for result in results]),
        turn_pass_rate=_rate([score.passed for score in scores]),
        check_pass_rates={
            name: _rate([score.checks[name] for score in scores if name in score.checks])
            for name in sorted(names)
        },
        average_latency_ms=sum(score.latency_ms for score in scores) / len(scores) if scores else 0.0,
        failure_reasons={
            reason: sum(score.guardrail_reason == reason for score in scores)
            for reason in (
                "out_of_scope",
                "insufficient_evidence",
                "generation_validation_failed",
            )
        },
    )


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0
