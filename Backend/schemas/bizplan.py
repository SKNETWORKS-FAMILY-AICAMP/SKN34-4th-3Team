from __future__ import annotations

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


class BusinessPlanResponse(BaseModel):
    model_config = ConfigDict(title="사업계획서 초안 (PSST)")
    problem: str = Field(description="Problem — 문제 인식")
    solution: str = Field(description="Solution — 실현 가능성")
    scaleUp: str = Field(description="Scale-up — 성장 전략")
    team: str = Field(description="Team — 팀 구성")
    summary: str = Field(description="세 줄 요약")
    llmUsed: bool = Field(description="AI가 실제로 생성했는지 여부")
