from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessPlanReviewedSection(BaseModel):
    key: str = Field(max_length=100)
    label: str = Field(max_length=200)
    content: str = Field(max_length=5000)


class BusinessPlanRequest(BaseModel):
    model_config = ConfigDict(title="사업계획서 초안 요청")
    businessName: str = Field(default="", max_length=100, description="사업명")
    tagline: str = Field(default="", max_length=200, description="한 줄 소개")
    startupStatus: str = Field(default="", max_length=100, description="창업 상태")
    industry: str = Field(default="", max_length=100, description="업종")
    businessRegion: str = Field(default="", max_length=100, description="사업 지역")
    businessType: str = Field(default="", max_length=100, description="사업 형태")
    targetCustomer: str = Field(default="", max_length=500, description="목표 고객")
    problem: str = Field(default="", max_length=1000, description="핵심 문제")
    solution: str = Field(default="", max_length=1000, description="해결 방안")
    coreFeatures: str = Field(default="", max_length=1000, description="핵심 기능")
    differentiator: str = Field(default="", max_length=500, description="차별점")
    revenueModel: str = Field(default="", max_length=500, description="수익 방식")
    team: str = Field(default="", max_length=500, description="팀 구성")
    targetProgram: str = Field(default="", max_length=200, description="신청하려는 지원사업(선택)")
    extraNotes: str = Field(default="", max_length=1000, description="추가로 참고할 내용(선택)")
    templateText: str = Field(
        default="",
        max_length=12000,
        description="지원사업 공고의 사업계획서 양식 원문(선택). 비워두면 기본 양식 13개 항목으로 만든다.",
    )
    templateFields: list[str] = Field(default_factory=list, max_length=40)
    reviewedSections: list[BusinessPlanReviewedSection] = Field(default_factory=list, max_length=40)
    announcementId: int | None = Field(default=None, gt=0)


class BusinessPlanRefinedFields(BaseModel):
    model_config = ConfigDict(title="사업계획서 정리 대상")
    businessName: str = Field(default="", max_length=100)
    tagline: str = Field(default="", max_length=200)
    startupStatus: str = Field(default="", max_length=100)
    industry: str = Field(default="", max_length=100)
    businessRegion: str = Field(default="", max_length=100)
    businessType: str = Field(default="", max_length=100)
    targetCustomer: str = Field(default="", max_length=500)
    problem: str = Field(default="", max_length=1000)
    solution: str = Field(default="", max_length=1000)
    coreFeatures: str = Field(default="", max_length=1000)
    differentiator: str = Field(default="", max_length=500)
    revenueModel: str = Field(default="", max_length=500)
    team: str = Field(default="", max_length=500)
    extraNotes: str = Field(default="", max_length=1000)


class BusinessPlanRefineRequest(BaseModel):
    input: BusinessPlanRefinedFields


class BusinessPlanRefineResponse(BaseModel):
    refined: BusinessPlanRefinedFields
    llmUsed: bool


class BusinessPlanTemplateRequest(BaseModel):
    fileName: str = Field(min_length=1, max_length=255)
    contentBase64: str = Field(min_length=1, description="4 MiB 이하 PDF/HWPX의 Base64 본문")


class BusinessPlanTemplateResponse(BaseModel):
    kind: Literal["pdf", "hwpx"]
    fields: list[str]
    outputFormats: list[Literal["pdf", "hwpx"]]


class BusinessPlanSection(BaseModel):
    model_config = ConfigDict(title="사업계획서 항목")
    key: str = Field(description="항목 식별자(기본 모드: problem/solution/scaleUp/team)")
    label: str = Field(description="화면에 보여줄 항목 제목")
    content: str = Field(description="항목 내용")


class BusinessPlanResponse(BaseModel):
    model_config = ConfigDict(title="사업계획서 초안")
    sections: list[BusinessPlanSection] = Field(description="항목 목록 — 공고 양식을 넣으면 그 구성을 따른다")
    summary: str = Field(description="세 줄 요약")
    llmUsed: bool = Field(description="AI가 실제로 생성했는지 여부")


class BizplanChatMessage(BaseModel):
    model_config = ConfigDict(title="아이디어 어시스턴트 대화 한 줄")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class BizplanSectionInput(BaseModel):
    model_config = ConfigDict(title="지금까지 작성된 항목")
    key: str = Field(default="", max_length=100)
    label: str = Field(default="", max_length=200)
    content: str = Field(default="", max_length=5000)


class BizplanCoachRequest(BaseModel):
    model_config = ConfigDict(title="아이디어 어시스턴트 질문")
    question: str = Field(min_length=1, max_length=1000)
    businessName: str = Field(default="", max_length=100)
    tagline: str = Field(default="", max_length=200)
    targetCustomer: str = Field(default="", max_length=500)
    sections: list[BizplanSectionInput] = Field(default_factory=list, max_length=20)
    conversationHistory: list[BizplanChatMessage] = Field(default_factory=list, max_length=20)


class BizplanCoachResponse(BaseModel):
    model_config = ConfigDict(title="아이디어 어시스턴트 답변")
    answer: str
    inScope: bool
    redirect: Literal["tax", "policy", "none"]


class BusinessPlanEvaluateRequest(BaseModel):
    model_config = ConfigDict(title="사업계획서 예비진단 요청")
    sections: list[BizplanSectionInput] = Field(default_factory=list, max_length=40, description="채점할 항목 목록")
    announcementId: int | None = Field(default=None, gt=0)
    templateFields: list[str] = Field(default_factory=list, max_length=40)


class BusinessPlanImageInput(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    mimeType: Literal["image/png", "image/jpeg"]
    contentBase64: str = Field(min_length=1, max_length=2_796_204)


class BusinessPlanRenderRequest(BaseModel):
    title: str = Field(default="사업계획서", max_length=200)
    sections: list[BizplanSectionInput] = Field(min_length=1, max_length=40)
    format: Literal["pdf", "hwpx"]
    template: BusinessPlanTemplateRequest | None = None
    images: list[BusinessPlanImageInput] = Field(default_factory=list, max_length=20)


class BusinessPlanRenderResponse(BaseModel):
    fileName: str
    mimeType: str
    contentBase64: str


class BusinessPlanSectionScore(BaseModel):
    model_config = ConfigDict(title="항목별 예비진단")
    key: str
    label: str
    score: int = Field(ge=0, le=100, description="0~100점")
    strengths: str = Field(description="잘된 점")
    improvements: str = Field(description="보완할 점")


class BusinessPlanEvaluateResponse(BaseModel):
    model_config = ConfigDict(title="사업계획서 예비진단 결과")
    overallScore: int = Field(ge=0, le=100, description="총점(0~100)")
    overallComment: str = Field(description="한 줄 총평")
    sections: list[BusinessPlanSectionScore] = Field(description="항목별 점수·강점·보완점")
    llmUsed: bool = Field(description="AI가 실제로 채점했는지 여부")


class BizplanDraftSave(BaseModel):
    model_config = ConfigDict(title="사업계획서 임시저장 요청")
    data: dict = Field(description="작성 화면 상태 전체(양식·이미지 Base64 포함, 12 MiB 이하)")


class BizplanDraftResponse(BaseModel):
    model_config = ConfigDict(title="사업계획서 임시저장 조회")
    data: dict | None = Field(default=None, description="저장된 작성 화면 상태. 없으면 null")
    updatedAt: datetime | None = Field(default=None, description="마지막 저장 시각")
