import logging
from datetime import date

from fastapi import HTTPException

from core import repo
from core.llm_client import rag_answer

logger = logging.getLogger(__name__)

# 공고 본문 전문을 20건 보내면 LLM 컨텍스트가 넘치므로 앞부분만 넘긴다.
NOTICE_TEXT_LIMIT = 800

# 대화 문맥 계약(CHAT_MEMORY_OVERVIEW.md 3절). 완료된 10쌍 = 메시지 20개까지만 보낸다.
HISTORY_TURN_LIMIT = 10
HISTORY_QUESTION_LIMIT = 1000
HISTORY_ANSWER_LIMIT = 4000
HISTORY_TOTAL_LIMIT = 12000
ROADMAP_HISTORY_TURN_LIMIT = 5
ROADMAP_HISTORY_TOTAL_LIMIT = 4000

SUGGESTED = {
    "tax": [
        "부가가치세는 언제 신고하나요?",
        "간이과세자와 일반과세자 차이는 무엇인가요?",
        "청년창업 세액감면 대상인지 알고 싶어요.",
    ],
    "expense": [
        "커피 영수증도 경비처리가 되나요?",
        "노트북 구매는 어떻게 비용 처리하나요?",
        "접대비와 복리후생비는 어떻게 구분하나요?",
    ],
    "saving": [
        "1인 창업자가 당장 챙길 절세 포인트는?",
        "홈택스에서 확인할 공제 항목이 있나요?",
        "사업용 계좌를 꼭 써야 하나요?",
    ],
    "policy": [
        "지금 신청 가능한 청년 창업 지원금이 있나요?",
        "예비창업패키지 자격 조건을 알려주세요.",
        "서울 거주 창업자가 받을 수 있는 정책은?",
    ],
    "roadmap": [
        "지원사업 신청 단계에서 뭘 준비해야 하나요?",
        "세액감면 신청 전에 확인할 일은 무엇인가요?",
        "초기 창업자는 어떤 순서로 자금을 준비하나요?",
    ],
}

MOCK_ANSWERS = {
    "tax": "세금 일정과 신고 유형은 사업자 등록 유형에 따라 달라집니다. LLM 서비스에 연결되지 않아 샘플 안내입니다. 실제 신고 전에는 국세청 자료 또는 세무 전문가 확인이 필요합니다.",
    "expense": "사업과 직접 관련된 지출은 증빙이 있으면 경비로 볼 여지가 있습니다. 최종 인정 여부는 세무서·세무사 확인이 필요합니다.",
    "saving": "장부 구분, 사업용 계좌, 감면 요건 확인이 기본입니다. 본 답변은 세무 자문을 대체하지 않습니다.",
    "policy": "사용자 나이·지역·업력을 기준으로 안내합니다. 실제 자격은 공고문 원문을 확인해야 합니다.",
    "roadmap": "현재 AI 코치에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
}

NON_CONTEXT_ANSWERS = frozenset(
    {
        "이 질문은 AI 세무 Assistant에서 확인해 주세요.",
        "이 질문은 공고지원 AI에서 확인해 주세요.",
        "창업 로드맵 단계와 준비 작업에 관한 질문만 답변할 수 있습니다.",
        "현재 실제 데이터를 조회하거나 계산할 수 없습니다.",
        "요청을 처리하는 중 오류가 발생했습니다.",
    }
)


def suggested_questions(category: str) -> list[str]:
    return SUGGESTED.get(category, SUGGESTED["tax"])


def _profile_prefix(user_id: int) -> str:
    user = repo.get_user(user_id) or {}
    profile = repo.get_profile(user_id) or {}
    context = f"{user.get('name') or '회원'}님"
    extras = [x for x in (user.get("region"), profile.get("industry")) if x]
    if extras:
        context += f"({', '.join(extras)})"
    return context


def _date_str(value) -> str | None:
    """LLM 계약의 날짜 필드는 YYYY-MM-DD 문자열이다."""
    if not value:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _clip(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:NOTICE_TEXT_LIMIT]


def _user_context(user_id: int) -> dict | None:
    """`RagChatRequest.userContext`. BackendUserContext는 extra="forbid"라 필드를 하나씩 만든다."""
    user = repo.get_user(user_id)
    if not user:
        return None
    profile = repo.get_profile(user_id) or {}
    age = user.get("age")
    return {
        "userId": user["id"],
        # 계약이 0~150만 허용한다. 벗어난 값을 보내면 요청 전체가 422가 된다.
        "age": age if isinstance(age, int) and 0 <= age <= 150 else None,
        "region": user.get("region"),
        "businessType": profile.get("business_type"),
        "industry": profile.get("industry"),
        "businessRegisteredAt": _date_str(profile.get("business_registered_at")),
        "foundedAt": _date_str(profile.get("founded_at")),
    }


def _notice_results() -> list[dict]:
    """`RagChatRequest.noticeResults`. BackendNoticeResult도 extra="forbid"다."""
    notices = []
    for row in repo.open_announcements():
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        notices.append(
            {
                "announcementId": row["id"],
                "policyId": row.get("policy_id"),
                "title": title,
                "content": _clip(row.get("raw_content")),
                "benefit": _clip(row.get("benefit")),
                "sourceUrl": row.get("source_url"),
                "applyStartDate": _date_str(row.get("apply_start_date")),
                "applyEndDate": _date_str(row.get("apply_end_date")),
            }
        )
    return notices


def _conversation_history(user_id: int, category: str) -> list[dict]:
    """`RagChatRequest.conversationHistory`. 같은 사용자·카테고리의 지난 대화만 담는다.

    과거 답변은 후속 질문을 이해하기 위한 문맥일 뿐 법적 근거나 인용 출처가 아니다.
    """
    turn_limit = (
        ROADMAP_HISTORY_TURN_LIMIT
        if category == "roadmap"
        else HISTORY_TURN_LIMIT
    )
    total_limit = (
        ROADMAP_HISTORY_TOTAL_LIMIT
        if category == "roadmap"
        else HISTORY_TOTAL_LIMIT
    )
    pairs: list[tuple[str, str]] = []
    for row in repo.recent_chats(user_id, category, turn_limit):
        question = str(row.get("question") or "").strip()[:HISTORY_QUESTION_LIMIT]
        answer = str(row.get("answer") or "").strip()[:HISTORY_ANSWER_LIMIT]
        # 한쪽이 비면 user→assistant 쌍을 유지할 수 없어 통째로 뺀다.
        if not question or not answer:
            continue
        if answer in NON_CONTEXT_ANSWERS or any(
            mock_answer in answer for mock_answer in MOCK_ANSWERS.values()
        ):
            continue
        pairs.append((question, answer))

    total = sum(len(question) + len(answer) for question, answer in pairs)
    while pairs and total > total_limit:
        question, answer = pairs.pop(0)
        total -= len(question) + len(answer)

    history: list[dict] = []
    for question, answer in pairs:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
    return history


def _sources_from_rag(rag: dict) -> list[dict]:
    sources = []
    for item in rag.get("sources") or []:
        sources.append(
            {
                "title": item.get("title") or item.get("source") or "RAG 문서",
                # url은 사용자에게 보여줄 링크, source는 원천 식별자로 별도 필드다.
                "url": item.get("url") or "",
                "excerpt": item.get("excerpt") or "",
            }
        )
    return sources


def send_message(
    user_id: int,
    category: str,
    question: str,
    *,
    roadmap_step: str | None = None,
) -> dict:
    if category not in SUGGESTED:
        raise HTTPException(status_code=400, detail="지원하지 않는 카테고리입니다.")
    # 현재 질문은 question으로만 보낸다. 저장은 LLM 응답 이후라 여기서는 중복되지 않는다.
    history = _conversation_history(user_id, category)
    rag = rag_answer(
        question,
        category=category,
        conversation_history=history or None,
        roadmap_step=roadmap_step,
        # 프로필은 질문 문자열이 아니라 계약 필드로 보낸다.
        user_context=_user_context(user_id),
        # 라우터가 policy와 notice 중 무엇을 고를지 미리 알 수 없으므로 policy에는 항상 보낸다.
        # 보내지 않으면 notice route가 integration_unavailable로 끝난다.
        notice_results=_notice_results() if category == "policy" else None,
    )
    status = rag.get("status") if rag else None
    guardrail = rag.get("guardrail_reason") if rag else None
    # LLM이 200으로 답했으면 status가 무엇이든 그 문장을 그대로 보존한다.
    # 답변 생성은 LLM 책임이므로(V1 10절) 목업은 LLM에 닿지 못했을 때만 쓴다.
    usable = bool(rag and rag.get("answer"))

    if not usable:
        # 이 경로는 llm_client의 경고가 안 찍힐 수도 있어 여기서 따로 남긴다.
        logger.warning(
            "Chat fallback to mock: category=%s reason=%s",
            category,
            "llm_unreachable" if rag is None else "empty_answer",
        )
        status = "integration_unavailable"
        guardrail = None
        if category == "roadmap":
            full_answer = MOCK_ANSWERS[category]
        else:
            full_answer = (
                f"{_profile_prefix(user_id)} 질문: “{question}”\n\n{MOCK_ANSWERS[category]}\n\n"
                "※ 근거 문서를 확인하지 못한 참고 안내입니다. 국세청·공고 원문 또는 전문가 확인이 필요합니다."
            )
        sources = []
        grounded = False
        llm_used = False
        needs_confirmation = True
    else:
        full_answer = rag["answer"]
        sources = _sources_from_rag(rag)
        grounded = bool(rag.get("grounded"))
        llm_used = True
        needs_confirmation = status != "success"
        if needs_confirmation:
            logger.warning(
                "Chat answer not grounded: category=%s status=%s guardrail=%s",
                category,
                status,
                guardrail,
            )
        if guardrail == "out_of_scope":
            # status는 no_result지만 근거 부족이 아니라 범위 밖 질문이다.
            sources = []
            grounded = False

    mid = repo.insert_chat(user_id, category, question, full_answer, sources)
    return {
        "messageId": mid,
        "answer": full_answer,
        "grounded": grounded,
        "llmUsed": llm_used,
        "needsConfirmation": needs_confirmation,
        # 프론트가 "LLM이 답했지만 실패"와 "근거 있게 답함"을 구분하려면 status가 필요하다.
        "status": status,
        "guardrailReason": guardrail,
    }


def get_sources(message_id: int, user_id: int) -> list[dict]:
    message = repo.get_chat(message_id)
    # 남의 메시지는 존재 사실 자체를 숨기려고 403이 아니라 404로 답한다.
    # 관리자 예외는 두지 않는다. 관리자 토큰의 id는 사용자 메시지와 일치하지 않는다.
    if not message or message.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
    return repo.chat_sources(message_id)


def list_messages(user_id: int, category: str | None = None) -> list[dict]:
    return repo.list_chats(user_id, category)


def clear_messages(user_id: int, category: str | None = None) -> int:
    return repo.delete_chats(user_id, category)


def delete_messages(user_id: int, message_ids: list[int]) -> int:
    """대화방 하나(메시지 묶음)만 지운다. 다른 사용자 소유의 id는 무시된다."""
    return repo.delete_chats_by_ids(user_id, message_ids)
