import pytest

from src.evaluation.metrics import (
    average_precision_at_k,
    guardrail_metrics,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    retrieval_metrics,
)


def test_notebook_ranking_example_metrics() -> None:
    predicted = [99, 1, 98, 2, 3]
    relevant = {1, 2, 3}

    metrics = retrieval_metrics(predicted, relevant, k=5)

    assert metrics.precision_at_k == pytest.approx(0.6)
    assert metrics.recall_at_k == pytest.approx(1.0)
    assert metrics.reciprocal_rank == pytest.approx(0.5)
    assert metrics.average_precision == pytest.approx((0.5 + 0.5 + 0.6) / 3)


def test_average_precision_penalizes_missed_relevant_policies() -> None:
    assert average_precision_at_k([1], {1, 2, 3}, k=5) == pytest.approx(1 / 3)


def test_duplicate_predictions_do_not_count_as_repeated_hits() -> None:
    predicted = [1, 1, 2]
    relevant = {1, 2}

    assert precision_at_k(predicted, relevant, k=3) == pytest.approx(2 / 3)
    assert recall_at_k(predicted, relevant, k=3) == pytest.approx(1.0)
    assert reciprocal_rank(predicted, relevant) == pytest.approx(1.0)


def test_empty_relevant_set_has_zero_retrieval_scores() -> None:
    assert precision_at_k([1, 2], set(), k=2) == 0.0
    assert recall_at_k([1, 2], set(), k=2) == 0.0
    assert reciprocal_rank([1, 2], set()) == 0.0
    assert average_precision_at_k([1, 2], set(), k=2) == 0.0


def test_guardrail_binary_classification_metrics() -> None:
    metrics = guardrail_metrics(
        expected_blocks=[True, True, False, False],
        predicted_blocks=[True, False, True, False],
    )

    assert metrics.accuracy == pytest.approx(0.5)
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.f1 == pytest.approx(0.5)
    assert metrics.true_positive == 1
    assert metrics.false_positive == 1
    assert metrics.true_negative == 1
    assert metrics.false_negative == 1


@pytest.mark.parametrize("metric", [precision_at_k, recall_at_k, average_precision_at_k])
def test_metrics_reject_invalid_k(metric: object) -> None:
    with pytest.raises(ValueError, match="k must be at least 1"):
        metric([1], {1}, 0)
