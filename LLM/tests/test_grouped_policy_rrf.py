import pytest

from src.vectorstores.nori_hybrid import source_level_rrf
from tests.test_nori_hybrid_live import doc


def test_same_backend_repetition_does_not_accumulate_and_keeps_best_rank():
    a, b, c = [doc(i, policy_id=i) for i in (1, 2, 3)]
    rankings = [[a, b], [c, a]]
    result = source_level_rrf(rankings, unit="policy", rrf_k=60, top_k=20,
        ranking_groups=["dense", "dense"])
    scores = {d["policy_id"]: d["score"] for d in result}
    assert scores[1] == scores[3] == pytest.approx(1.0)
    assert scores[2] == pytest.approx(61 / 62)
    repeated = source_level_rrf([*rankings, rankings[0]], unit="policy", rrf_k=60, top_k=20,
        ranking_groups=["dense", "dense", "dense"])
    assert repeated == result
    legacy = source_level_rrf(rankings, unit="policy", rrf_k=60, top_k=20)
    assert legacy[0]["policy_id"] == 1
    assert legacy[0]["score"] > next(d["score"] for d in legacy if d["policy_id"] == 3)


def test_agreement_between_backends_still_adds_contributions():
    a, b = [doc(i, policy_id=i) for i in (1, 2)]
    result = source_level_rrf([[b, a], [b, a], [a]], unit="policy", rrf_k=60, top_k=20,
        ranking_groups=["dense", "dense", "bm25"])
    assert [d["policy_id"] for d in result] == [1, 2]
    assert result[0]["score"] == pytest.approx((1 / 62 + 1 / 61) / (2 / 61))
    assert result[1]["score"] == pytest.approx(0.5)


def test_grouped_rrf_handles_empty_rankings_and_duplicate_chunks():
    a, b = [doc(i, policy_id=i) for i in (1, 2)]
    duplicate = doc(1, policy_id=1, chunk=1)
    result = source_level_rrf([[a, duplicate, b], []], unit="policy", rrf_k=60, top_k=20,
        ranking_groups=["dense", "bm25"])
    assert len(result) == 2
    assert result[1]["score"] == pytest.approx((1 / 62) / (2 / 61))
    assert source_level_rrf([], unit="policy", rrf_k=60, top_k=20, ranking_groups=[]) == []
    with pytest.raises(ValueError, match="match rankings"):
        source_level_rrf([[a]], unit="policy", rrf_k=60, top_k=20, ranking_groups=[])
