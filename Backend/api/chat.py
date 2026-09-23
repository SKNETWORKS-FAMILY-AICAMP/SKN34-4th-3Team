from ninja import Router, Path, Query
from ninja.errors import HttpError

from api.deps import user_auth
from schemas.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatRoomRenameRequest,
    ChatRoomsResponse,
    SourcesResponse,
    SuggestedQuestionsResponse,
)
from services import chat_service

router = Router(tags=["상담"], auth=user_auth)


@router.get(
    "/categories/{category}/suggested-questions",
    response=SuggestedQuestionsResponse,
    auth=None,
    summary="추천 질문 목록",
)
def suggested(
    request,
    category: str = Path(
        description="카테고리: tax / expense / saving / policy / roadmap"
    ),
):
    """카테고리별 추천 질문입니다."""
    return {"category": category, "questions": chat_service.suggested_questions(category)}


@router.post("/messages", response=ChatMessageResponse, summary="챗봇 질문 보내기")
def send_message(request, body: ChatMessageRequest):
    """LLM RAG를 우선 호출하고, 실패하면 목업 답변을 저장합니다."""
    return chat_service.send_message(
        request.auth["id"],
        body.category,
        body.question,
        roadmap_step=body.roadmapStep,
        room_id=body.roomId,
    )


@router.get("/messages", summary="대화 히스토리 조회")
def history(
    request,
    category: str | None = Query(default=None, description="카테고리 필터(선택)"),
):
    """로그인한 사용자의 질문·답변 목록입니다."""
    return {"messages": chat_service.list_messages(request.auth["id"], category)}


@router.delete("/messages", summary="대화 기록 삭제")
def clear_history(
    request,
    category: str | None = Query(default=None, description="비우면 전체, 있으면 해당 카테고리만"),
    ids: str | None = Query(default=None, include_in_schema=False),
):
    """현재 사용자의 대화방을 모두(또는 해당 카테고리만) 삭제합니다. 삭제한 방은 목록·기록에서 빠집니다."""
    # 예전 프론트의 방 하나 삭제(?ids=)가 전체 삭제로 처리되지 않도록 막는다.
    if ids is not None:
        raise HttpError(400, "대화방 삭제는 DELETE /chat/rooms/{roomId}를 사용하세요. 새로고침 후 다시 시도해 주세요.")
    deleted = chat_service.clear_messages(request.auth["id"], category)
    return {"deleted": True, "count": deleted}


@router.get("/rooms", response=ChatRoomsResponse, summary="대화방 목록")
def rooms(
    request,
    category: str = Query(description="카테고리: tax / expense / saving / policy / roadmap"),
):
    """로그인한 사용자의 대화방을 최근 대화 순으로 반환합니다."""
    return {"rooms": chat_service.list_rooms(request.auth["id"], category)}


@router.patch("/rooms/{room_id}", summary="대화방 이름 변경")
def rename_room(request, body: ChatRoomRenameRequest, room_id: int = Path(description="대화방 ID")):
    """이름을 비우면 첫 질문을 제목으로 보여줍니다. 본인 방만 바꿀 수 있습니다."""
    chat_service.rename_room(request.auth["id"], room_id, body.title)
    return {"updated": True}


@router.delete("/rooms/{room_id}", summary="대화방 삭제")
def delete_room(request, room_id: int = Path(description="대화방 ID")):
    """본인 대화방 하나를 삭제합니다."""
    chat_service.delete_room(request.auth["id"], room_id)
    return {"deleted": True}


@router.get(
    "/messages/{message_id}/sources",
    response=SourcesResponse,
    summary="답변 근거 문서 조회",
)
def sources(
    request,
    message_id: int = Path(description="메시지 ID"),
):
    """해당 답변에 저장된 RAG 또는 샘플 근거 문서를 반환합니다. 본인 메시지만 조회됩니다."""
    return {"sources": chat_service.get_sources(message_id, request.auth["id"])}
