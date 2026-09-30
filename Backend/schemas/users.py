from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserMeResponse(BaseModel):
    model_config = ConfigDict(title="내 개인정보")
    id: int = Field(description="사용자 ID")
    email: str = Field(description="이메일")
    name: str = Field(description="이름")
    age: int | None = Field(default=None, description="나이")
    region: str | None = Field(default=None, description="거주 지역")
    phone: str | None = Field(default=None, description="휴대폰 번호")


class UserMeUpdate(BaseModel):
    model_config = ConfigDict(title="개인정보 수정")
    name: str | None = Field(default=None, description="이름")
    age: int | None = Field(default=None, description="나이")
    region: str | None = Field(default=None, description="거주 지역")
    phone: str | None = Field(default=None, description="휴대폰 번호")


class BusinessProfileResponse(BaseModel):
    model_config = ConfigDict(title="사업자 정보")
    businessType: str | None = Field(default=None, description="사업자 유형")
    industry: str | None = Field(default=None, description="업종")
    businessRegisteredAt: date | None = Field(default=None, description="사업자등록일")
    foundedAt: date | None = Field(default=None, description="창업일")


class BusinessProfileUpdate(BaseModel):
    model_config = ConfigDict(title="사업자 정보 수정")
    businessType: str | None = Field(default=None, description="사업자 유형")
    industry: str | None = Field(default=None, description="업종")
    businessRegisteredAt: date | None = Field(default=None, description="사업자등록일")
    foundedAt: date | None = Field(default=None, description="창업일")


class RoadmapProgressResponse(BaseModel):
    model_config = ConfigDict(title="창업 로드맵 진행 상태")
    version: int = Field(description="항목 구성 버전")
    done: list[str] = Field(description='완료한 항목 키 목록(예: "A:0")')


class RoadmapTaskUpdate(BaseModel):
    model_config = ConfigDict(title="창업 로드맵 항목 체크")
    taskKey: str = Field(pattern=r"^[A-Z]:\d+$", max_length=20, description='"단계:항목 인덱스" (예: "A:0")')
    done: bool = Field(description="완료 여부")


class PlanFeature(BaseModel):
    label: str = Field(description="기능명")
    value: bool | str = Field(description="제공 여부(true/false) 또는 제공 범위 문구")


class PlanItem(BaseModel):
    model_config = ConfigDict(title="구독 플랜")
    key: str = Field(description="플랜 키: free / basic / pro")
    name: str = Field(description="플랜 이름")
    price: int = Field(description="월 요금(원)")
    policyChatLimit: int | None = Field(description="공고지원 AI 상담 월 한도. null이면 무제한")
    features: list[PlanFeature] = Field(description="기능표 행")


class CurrentSubscription(BaseModel):
    plan: str = Field(description="현재 플랜 키")
    startedAt: datetime | None = Field(default=None, description="플랜 시작 시각")
    renewsAt: datetime | None = Field(default=None, description="다음 결제 예정 시각. 무료면 null")


class SubscriptionUsage(BaseModel):
    policyChat: int = Field(description="이번 달 공고지원 AI 상담 수")
    policyChatLimit: int | None = Field(description="현재 플랜의 공고지원 AI 상담 월 한도. null이면 무제한")
    taxChat: int = Field(description="이번 달 세무·경비·절세 상담 수(한도 없음)")


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(title="내 구독")
    plans: list[PlanItem] = Field(description="플랜 목록")
    current: CurrentSubscription = Field(description="현재 구독")
    usage: SubscriptionUsage = Field(description="이번 달 사용량")


class PlanChangeRequest(BaseModel):
    model_config = ConfigDict(title="플랜 변경(목업 결제)")
    plan: Literal["free", "basic", "pro"] = Field(description="바꿀 플랜 키")


class UpdatedResponse(BaseModel):
    model_config = ConfigDict(title="수정 결과")
    updated: bool = Field(default=True, description="수정 성공 여부")
