from copy import deepcopy

from src.data.contracts import EligibilityResult, Policy, RagChunk, UserProfile


class MockDataNotFoundError(LookupError):
    """요청한 테스트 데이터가 Mock 계층에 없을 때 발생한다."""


_USERS: dict[int, UserProfile] = {
    1: {
        "user_id": 1,
        "age": 29,
        "region": "서울",
        "business": {
            "industry": "음식점업",
            "business_type": "개인사업자",
            "founded_at": "2026-01-01",
        },
    },
    2: {
        "user_id": 2,
        "age": 34,
        "region": "부산",
        "business": {
            "industry": "제조업",
            "business_type": "개인사업자",
            "founded_at": "2024-03-15",
        },
    },
    3: {
        "user_id": 3,
        "age": None,
        "region": "서울",
        "business": {
            "industry": "서비스업",
            "business_type": "개인사업자",
            "founded_at": None,
        },
    },
    4: {
        "user_id": 4,
        "age": None,
        "region": None,
        "business": {
            "industry": None,
            "business_type": None,
            "founded_at": None,
        },
    },
}

_POLICIES: dict[int, Policy] = {
    101: {
        "policy_id": 101,
        "title": "청년창업 지원사업",
        "region": "서울",
        "industry": ["음식점업", "서비스업"],
        "apply_start_date": "2026-09-01",
        "apply_end_date": "2026-09-30",
    },
}

_ELIGIBILITY_RESULTS: dict[tuple[int, int], EligibilityResult] = {
    (1, 101): {
        "question": "나는 이 정책 대상이야?",
        "policy_id": 101,
        "eligible": True,
        "reasons": [
            "연령 조건 충족",
            "지역 조건 충족",
            "업종 조건 충족",
        ],
    },
    (2, 101): {
        "question": "나는 이 정책 대상이야?",
        "policy_id": 101,
        "eligible": False,
        "reasons": [
            "지역 조건 미충족",
            "업종 조건 미충족",
        ],
    },
    (3, 101): {
        "question": "정보가 부족해도 대상 여부를 확인할 수 있어?",
        "policy_id": 101,
        "eligible": False,
        "reasons": [
            "연령 정보 누락",
            "창업일 정보 누락",
        ],
    },
}

_RAG_CHUNKS: list[RagChunk] = [
    {
        "chunk_id": "policy-101-chunk-001",
        "policy_id": 101,
        "title": "청년창업 지원사업 테스트 문서",
        "source": "mock://policies/101",
        "page": 1,
        "content": (
            "이 테스트 정책은 서울 지역의 청년 창업자를 지원 대상으로 하며 "
            "신청자의 연령과 사업장 소재지를 확인한다."
        ),
    },
    {
        "chunk_id": "policy-101-chunk-002",
        "policy_id": 101,
        "title": "청년창업 지원사업 테스트 문서",
        "source": "mock://policies/101",
        "page": 2,
        "content": (
            "지원 업종에는 음식점업과 서비스업이 포함되며 신청 기간은 "
            "2026년 9월 1일부터 9월 30일까지이다."
        ),
    },
    {
        "chunk_id": "policy-102-chunk-001",
        "policy_id": 102,
        "title": "청년 주거이전비 지원사업 테스트 문서",
        "source": "mock://policies/102",
        "page": 1,
        "content": (
            "이 테스트 정책은 이사한 청년의 주거 이전 비용 일부를 지원한다."
        ),
    },
]


def get_user_profile(user_id: int) -> UserProfile:
    """Mock 사용자 프로필의 JSON 호환 복사본을 반환한다.

    Args:
        user_id: 조회할 Mock 사용자의 식별자.

    Returns:
        사용자·사업자 정보를 담은 Dictionary 복사본.

    Raises:
        MockDataNotFoundError: 해당 user_id의 Mock 사용자가 없을 때.
    """
    try:
        return deepcopy(_USERS[user_id])
    except KeyError as exc:
        raise MockDataNotFoundError(f"Mock user not found: {user_id}") from exc


def get_policy(policy_id: int) -> Policy:
    """Mock 정책 정보의 JSON 호환 복사본을 반환한다.

    Args:
        policy_id: 조회할 Mock 정책의 식별자.

    Returns:
        정책 기본 정보를 담은 Dictionary 복사본.

    Raises:
        MockDataNotFoundError: 해당 policy_id의 Mock 정책이 없을 때.
    """
    try:
        return deepcopy(_POLICIES[policy_id])
    except KeyError as exc:
        raise MockDataNotFoundError(f"Mock policy not found: {policy_id}") from exc


def get_eligibility_result(user_id: int, policy_id: int) -> EligibilityResult:
    """Backend가 계산했다고 가정한 Mock 판정 결과를 그대로 반환한다.

    Args:
        user_id: 판정 대상 Mock 사용자의 식별자.
        policy_id: 판정 대상 Mock 정책의 식별자.

    Returns:
        eligible과 reasons를 포함한 사전 계산 결과의 복사본.

    Raises:
        MockDataNotFoundError: 사용자와 정책 조합의 판정 결과가 없을 때.

    Notes:
        이 함수는 자격 조건을 계산하거나 기존 판정값을 변경하지 않는다.
    """
    eligibility_key = (user_id, policy_id)
    try:
        return deepcopy(_ELIGIBILITY_RESULTS[eligibility_key])
    except KeyError as exc:
        raise MockDataNotFoundError(
            f"Mock eligibility result not found: user={user_id}, policy={policy_id}"
        ) from exc


def get_rag_chunks(policy_id: int | None = None) -> list[RagChunk]:
    """선택한 정책으로 제한할 수 있는 Mock RAG Chunk를 반환한다.

    Args:
        policy_id: 검색 범위를 제한할 정책 ID. None이면 전체 Chunk를 반환한다.

    Returns:
        호출자가 원본을 변경할 수 없도록 복사한 Mock RAG Chunk 목록.
    """
    rag_chunks = (
        _RAG_CHUNKS
        if policy_id is None
        else [chunk for chunk in _RAG_CHUNKS if chunk["policy_id"] == policy_id]
    )
    return deepcopy(rag_chunks)
