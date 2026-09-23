from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(title="챗봇 질문")
    category: str = Field(
        description="카테고리: tax / expense / saving / policy / roadmap"
    )
    question: str = Field(description="질문 내용")
    roadmapStep: Literal["A", "B", "C", "D", "E", "F", "Z"] | None = Field(
        default=None,
        description="창업 로드맵의 현재 단계",
    )
    roomId: int | None = Field(
        default=None,
        description="이어 쓸 대화방 ID. 비우면 새 대화방을 만든다",
    )

    @model_validator(mode="after")
    def validate_roadmap_step(self) -> "ChatMessageRequest":
        if self.category != "roadmap" and self.roadmapStep is not None:
            raise ValueError("roadmapStep is only valid for roadmap category")
        return self


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(title="챗봇 답변")
    messageId: int = Field(description="메시지 ID")
    roomId: int = Field(description="메시지가 저장된 대화방 ID")
    answer: str = Field(description="답변 텍스트")
    grounded: bool = Field(default=False, description="RAG 근거가 있었는지")
    llmUsed: bool = Field(default=False, description="LLM 서비스 호출 여부")
    needsConfirmation: bool = Field(default=False, description="근거 부족으로 확인이 필요한지")
    status: str | None = Field(
        default=None,
        description="LLM 답변 상태(success·need_more_info·insufficient_evidence·no_result·integration_unavailable·error)",
    )
    guardrailReason: str | None = Field(
        default=None,
        description="Guardrail 사유(out_of_scope·insufficient_evidence·generation_validation_failed)",
    )


class SourceItem(BaseModel):
    model_config = ConfigDict(title="근거 문서")
    title: str = Field(description="문서 제목")
    url: str = Field(description="출처 URL")
    excerpt: str = Field(description="발췌 내용")


class SourcesResponse(BaseModel):
    model_config = ConfigDict(title="근거 문서 목록")
    sources: list[SourceItem] = Field(description="근거 문서들")


class SuggestedQuestionsResponse(BaseModel):
    model_config = ConfigDict(title="추천 질문")
    category: str = Field(description="카테고리")
    questions: list[str] = Field(description="추천 질문 목록")


class ChatRoomItem(BaseModel):
    model_config = ConfigDict(title="대화방")
    id: int = Field(description="대화방 ID")
    category: str = Field(description="카테고리")
    title: str | None = Field(default=None, description="직접 정한 이름. 없으면 firstQuestion을 제목으로 쓴다")
    firstQuestion: str | None = Field(default=None, description="첫 질문")
    createdAt: datetime | None = Field(default=None, description="생성 시각")
    updatedAt: datetime | None = Field(default=None, description="마지막 메시지 시각")


class ChatRoomsResponse(BaseModel):
    model_config = ConfigDict(title="대화방 목록")
    rooms: list[ChatRoomItem] = Field(description="최근 대화 순 대화방")


class ChatRoomRenameRequest(BaseModel):
    model_config = ConfigDict(title="대화방 이름 변경")
    title: str | None = Field(default=None, max_length=255, description="새 이름. 비우면 첫 질문으로 되돌린다")
