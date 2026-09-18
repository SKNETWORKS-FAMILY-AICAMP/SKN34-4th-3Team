from pydantic import BaseModel, ConfigDict, Field


class StatsResponse(BaseModel):
    model_config = ConfigDict(title="서비스 지표")
    openAnnouncements: int = Field(description="마감이 지나지 않은 공고 수")
    policies: int = Field(description="수집된 지원정책 수")
    taxDocuments: int = Field(description="수집된 세법 조문 수")
    maxReductionRate: int = Field(
        description="청년창업 세액감면 최대 감면율(%). DB 집계가 아니라 법령 기반 고정값"
    )
