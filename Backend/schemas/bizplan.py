from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessPlanRequest(BaseModel):
    model_config = ConfigDict(title="사업계획서 초안 요청")
    businessName: str = Field(default="", max_length=100, description="사업명")
    tagline: str = Field(default="", max_length=200, description="한 줄 소개")
    targetCustomer: str = Field(default="", max_length=500, description="목표 고객")
    problem: str = Field(default="", max_length=1000, description="핵심 문제")
    solution: str = Field(default="", max_length=1000, description="해결 방안")
    differentiator: str = Field(default="", max_length=500, description="차별점")
    team: str = Field(default="", max_length=500, description="팀 구성")
    targetProgram: str = Field(default="", max_length=200, description="신청하려는 지원사업(선택)")
    extraNotes: str = Field(default="", max_length=1000, description="추가로 참고할 내용(선택)")
    templateText: str = Field(
        default="",
        max_length=6000,
        description="지원사업 공고의 사업계획서 양식 원문(선택). 비워두면 기본 PSST 4항목으로 만든다.",
    )


class BusinessPlanTemplateFileResponse(BaseModel):
    model_config = ConfigDict(title="공고 양식 파일 추출 결과")
    templateText: str = Field(description="업로드한 PDF에서 추출한 텍스트. BusinessPlanRequest.templateText로 그대로 쓴다")


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
    content: str = Field(default="", max_length=2000)


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
    sections: list[BizplanSectionInput] = Field(default_factory=list, max_length=20, description="채점할 항목 목록")


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
