import json

import pytest

from src.data import (
    MockDataNotFoundError,
    get_eligibility_result,
    get_policy,
    get_user_profile,
)


def test_eligible_result_is_returned_without_recalculation() -> None:
    result = get_eligibility_result(user_id=1, policy_id=101)

    assert result["eligible"] is True
    assert result["reasons"] == [
        "연령 조건 충족",
        "지역 조건 충족",
        "업종 조건 충족",
    ]


def test_ineligible_result_is_available() -> None:
    result = get_eligibility_result(user_id=2, policy_id=101)

    assert result["eligible"] is False
    assert "지역 조건 미충족" in result["reasons"]


def test_missing_profile_values_are_preserved_as_none() -> None:
    user = get_user_profile(user_id=3)

    assert user["age"] is None
    assert user["business"]["founded_at"] is None


def test_returned_data_cannot_mutate_the_shared_mock_fixture() -> None:
    policy = get_policy(policy_id=101)
    policy["industry"].append("변경 테스트")

    fresh_policy = get_policy(policy_id=101)
    assert "변경 테스트" not in fresh_policy["industry"]


def test_mock_records_are_json_serializable() -> None:
    payload = {
        "user": get_user_profile(user_id=1),
        "policy": get_policy(policy_id=101),
        "eligibility": get_eligibility_result(user_id=1, policy_id=101),
    }

    assert json.loads(json.dumps(payload, ensure_ascii=False)) == payload


def test_unknown_mock_record_raises_clear_error() -> None:
    with pytest.raises(MockDataNotFoundError, match="Mock user not found"):
        get_user_profile(user_id=999)
