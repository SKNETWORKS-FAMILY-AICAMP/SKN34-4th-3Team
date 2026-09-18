from pydantic import BaseModel, ConfigDict, Field


class DiagnosisRequest(BaseModel):
    model_config = ConfigDict(title="사업자 유형 진단 요청")
    conditions: dict = Field(description="진단 조건. 예: expectedRevenue, hasEmployee")


class DiagnosisResponse(BaseModel):
    model_config = ConfigDict(title="사업자 유형 진단 결과")
    recommendedType: str = Field(description="추천 유형")
    comparison: list[dict] = Field(description="유형별 비교")


class TaxInfoResponse(BaseModel):
    model_config = ConfigDict(title="세금 정보")
    taxInfo: dict = Field(description="세금 메모")


class TaxInfoUpdate(BaseModel):
    model_config = ConfigDict(title="세금 정보 수정")
    taxInfo: dict = Field(description="저장할 세금 메모")


class TaxReductionResponse(BaseModel):
    model_config = ConfigDict(title="세액감면 판정 결과")
    eligible: bool = Field(description="요건 충족 여부")
    reasons: list[str] = Field(description="판정 사유")
    legalBasis: str = Field(description="근거 안내")
    llmUsed: bool = Field(default=False, description="LLM 설명 생성 여부")
