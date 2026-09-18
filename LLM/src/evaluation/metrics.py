from collections.abc import Iterable

from pydantic import BaseModel


class RetrievalMetrics(BaseModel):
    """평가 케이스 한 건의 P@k, R@k, RR과 AP@k."""

    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    average_precision: float


class GuardrailMetrics(BaseModel):
    """차단을 Positive로 정의한 Guardrail 이진 분류 지표."""

    accuracy: float
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


def precision_at_k(predicted: Iterable[int], relevant: set[int], k: int) -> float:
    """상위 k개 정책 중 관련 정책이 차지하는 비율 P@k를 계산한다.

    Args:
        predicted: 관련성 순서로 반환된 예측 policy_id.
        relevant: 평가자가 정답으로 지정한 policy_id 집합.
        k: 평가할 상위 검색 결과 개수.

    Returns:
        `상위 k개 내 관련 정책 수 / k` 값. 정답이 없으면 0.

    Raises:
        ValueError: k가 1보다 작을 때.
    """
    _validate_k(k)
    relevant_hits = _relevant_hits(predicted, relevant, k)
    return len(relevant_hits) / k


def recall_at_k(predicted: Iterable[int], relevant: set[int], k: int) -> float:
    """전체 관련 정책 중 상위 k개에서 찾은 비율 R@k를 계산한다.

    Args:
        predicted: 관련성 순서로 반환된 예측 policy_id.
        relevant: 평가자가 정답으로 지정한 policy_id 집합.
        k: 평가할 상위 검색 결과 개수.

    Returns:
        `상위 k개 내 관련 정책 수 / 전체 관련 정책 수` 값. 정답이 없으면 0.

    Raises:
        ValueError: k가 1보다 작을 때.
    """
    _validate_k(k)
    if not relevant:
        return 0.0
    relevant_hits = _relevant_hits(predicted, relevant, k)
    return len(relevant_hits) / len(relevant)


def reciprocal_rank(predicted: Iterable[int], relevant: set[int]) -> float:
    """첫 관련 정책 순위의 역수 RR을 계산한다.

    Args:
        predicted: 관련성 순서로 반환된 예측 policy_id.
        relevant: 평가자가 정답으로 지정한 policy_id 집합.

    Returns:
        첫 관련 정책의 `1 / 순위`. 관련 정책이 없으면 0.
    """
    if not relevant:
        return 0.0
    for rank, policy_id in enumerate(_unique_ranking(predicted), start=1):
        if policy_id in relevant:
            return 1.0 / rank
    return 0.0


def average_precision_at_k(
    predicted: Iterable[int],
    relevant: set[int],
    k: int,
) -> float:
    """상위 k개 정책의 표준 Average Precision을 계산한다.

    Args:
        predicted: 관련성 순서로 반환된 예측 policy_id.
        relevant: 평가자가 정답으로 지정한 policy_id 집합.
        k: 평가할 상위 검색 결과 개수.

    Returns:
        관련 정책이 등장한 순위별 Precision 합을
        `min(전체 관련 정책 수, k)`로 나눈 AP@k. 정답이 없으면 0.

    Raises:
        ValueError: k가 1보다 작을 때.

    Notes:
        검색된 정답만 평균내지 않으므로 top-k에서 놓친 정답도 감점한다.
    """
    _validate_k(k)
    if not relevant:
        return 0.0

    relevant_count = 0
    precision_sum = 0.0
    for rank, policy_id in enumerate(_unique_ranking(predicted)[:k], start=1):
        if policy_id in relevant:
            relevant_count += 1
            precision_sum += relevant_count / rank
    return precision_sum / min(len(relevant), k)


def retrieval_metrics(
    predicted: Iterable[int],
    relevant: set[int],
    k: int,
) -> RetrievalMetrics:
    """정책 순위 한 건의 P@k, R@k, RR과 AP@k를 함께 계산한다.

    Args:
        predicted: 관련성 순서로 반환된 예측 policy_id.
        relevant: 평가자가 정답으로 지정한 policy_id 집합.
        k: 평가할 상위 검색 결과 개수.

    Returns:
        네 가지 검색 지표를 담은 RetrievalMetrics.
    """
    policy_ranking = list(predicted)
    return RetrievalMetrics(
        precision_at_k=precision_at_k(policy_ranking, relevant, k),
        recall_at_k=recall_at_k(policy_ranking, relevant, k),
        reciprocal_rank=reciprocal_rank(policy_ranking, relevant),
        average_precision=average_precision_at_k(policy_ranking, relevant, k),
    )


def guardrail_metrics(
    expected_blocks: Iterable[bool],
    predicted_blocks: Iterable[bool],
) -> GuardrailMetrics:
    """차단을 Positive로 정의해 Guardrail 이진 분류 지표를 계산한다.

    Args:
        expected_blocks: 평가자가 정의한 질문별 차단 필요 여부.
        predicted_blocks: 실제 Guardrail이 질문을 차단했는지 여부.

    Returns:
        Accuracy, Precision, Recall, F1과 TP·FP·TN·FN 개수를 담은 결과.

    Raises:
        ValueError: 기대값과 예측값의 개수가 다를 때.

    Notes:
        Positive는 차단해야 하는 질문, Negative는 허용해야 하는 질문이다.
    """
    classification_pairs = list(
        zip(expected_blocks, predicted_blocks, strict=True)
    )
    true_positive = sum(
        expected_block and predicted_block
        for expected_block, predicted_block in classification_pairs
    )
    false_positive = sum(
        not expected_block and predicted_block
        for expected_block, predicted_block in classification_pairs
    )
    true_negative = sum(
        not expected_block and not predicted_block
        for expected_block, predicted_block in classification_pairs
    )
    false_negative = sum(
        expected_block and not predicted_block
        for expected_block, predicted_block in classification_pairs
    )

    case_count = len(classification_pairs)
    accuracy = (
        (true_positive + true_negative) / case_count if case_count else 0.0
    )
    precision = _safe_divide(true_positive, true_positive + false_positive)
    recall = _safe_divide(true_positive, true_positive + false_negative)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    return GuardrailMetrics(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        f1=f1,
        true_positive=true_positive,
        false_positive=false_positive,
        true_negative=true_negative,
        false_negative=false_negative,
    )


def _relevant_hits(predicted: Iterable[int], relevant: set[int], k: int) -> set[int]:
    """중복을 제거한 상위 k개에서 관련 policy_id 집합을 반환한다."""
    return set(_unique_ranking(predicted)[:k]).intersection(relevant)


def _unique_ranking(predicted: Iterable[int]) -> list[int]:
    """최초 등장 순서를 유지하면서 중복 policy_id를 제거한다."""
    return list(dict.fromkeys(predicted))


def _validate_k(k: int) -> None:
    """k가 검색 평가에 사용할 수 있는 양의 정수인지 검사한다."""
    if k < 1:
        raise ValueError("k must be at least 1")


def _safe_divide(numerator: float, denominator: float) -> float:
    """분모가 0이면 0을 반환하는 안전한 나눗셈을 수행한다."""
    return numerator / denominator if denominator else 0.0
