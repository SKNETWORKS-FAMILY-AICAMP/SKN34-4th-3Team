from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class PolicyItem(BaseModel):
    model_config = ConfigDict(title="지원정책")
    policyId: int = Field(description="정책 ID")
    title: str = Field(description="정책명")
    # 아래 다섯 컬럼은 DB에서 전부 nullable이다. 원천 공고가 값을 주지 않으면 null로 나간다.
    region: str | None = Field(default=None, description="지역. 원천 공고에 지역 정보가 없으면 null")
    industry: str | None = Field(default=None, description="업종")
    target: str | None = Field(default=None, description="지원 대상")
    benefit: str | None = Field(default=None, description="지원 내용")
    source: str | None = Field(default=None, description="출처")
    sourceUrl: str | None = Field(default=None, description="공고 원문 URL")
    applyEndDate: date | None = Field(default=None, description="신청 마감일")
    matchScore: int | None = Field(default=None, description="맞춤 추천 점수(0~100)")
    eligible: bool | None = Field(
        default=None, description="자격 충족 여부. 공고에 요건이 없어 판정할 수 없으면 null"
    )


class PolicyListResponse(BaseModel):
    model_config = ConfigDict(title="정책 목록")
    policies: list[PolicyItem] = Field(description="정책들")


class PolicyDetailResponse(BaseModel):
    model_config = ConfigDict(title="정책 상세")
    policy: PolicyItem = Field(description="정책 정보")
    applyPeriod: str = Field(description="신청 기간. 원천 공고에 날짜가 없으면 빈 문자열")
    applyMethod: str | None = Field(
        default=None, description="신청 방법. 원천 공고에 신청 방법이 없으면 null"
    )
    announcementId: int | None = Field(default=None, description="공고 ID")


class EligibilityResponse(BaseModel):
    model_config = ConfigDict(title="자격 확인 결과")
    eligible: bool | None = Field(
        default=None, description="충족 여부. 공고에 요건이 없어 판정할 수 없으면 null"
    )
    reasons: list[str] = Field(description="판단 사유")


class AnnouncementItem(BaseModel):
    model_config = ConfigDict(title="모집 중 공고")
    id: int = Field(description="공고 ID")
    policyId: int = Field(description="정책 ID. 관심 저장에 쓰는 id")
    title: str = Field(description="정책명")
    dday: int | None = Field(
        default=None, description="마감까지 남은 일수. 마감일이 없으면 null"
    )
    region: str | None = Field(default=None, description="지역")
    industry: str | None = Field(default=None, description="업종")
    target: str | None = Field(default=None, description="지원 대상")
    benefit: str | None = Field(default=None, description="지원 내용")
    sourceUrl: str | None = Field(default=None, description="공고 원문 URL")


class AnnouncementListResponse(BaseModel):
    model_config = ConfigDict(title="모집 중 공고 목록")
    announcements: list[AnnouncementItem] = Field(description="마감 임박순 공고들")


class AnnouncementSummaryRequest(BaseModel):
    model_config = ConfigDict(title="공고문 요약 요청")
    rawContent: str = Field(
        min_length=1, max_length=20000, description="공고문 원문. 붙여넣은 텍스트"
    )
    source: str | None = Field(default=None, description="출처 표기(선택)")


class AnnouncementSummaryResponse(BaseModel):
    model_config = ConfigDict(title="공고문 요약")
    target: str = Field(description="지원 대상")
    benefit: str = Field(description="지원 내용")
    period: str = Field(description="기간")
    documents: str = Field(description="제출 서류")
    notes: str = Field(description="유의사항")
    source: str = Field(description="출처")
    llmUsed: bool = Field(default=False, description="LLM 요약 여부")


class SavedResponse(BaseModel):
    model_config = ConfigDict(title="관심 저장 결과")
    saved: bool = Field(default=True, description="저장 여부")
