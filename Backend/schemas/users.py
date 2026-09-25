from datetime import date

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


class UpdatedResponse(BaseModel):
    model_config = ConfigDict(title="수정 결과")
    updated: bool = Field(default=True, description="수정 성공 여부")
