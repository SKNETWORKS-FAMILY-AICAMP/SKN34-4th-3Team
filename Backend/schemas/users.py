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


class UpdatedResponse(BaseModel):
    model_config = ConfigDict(title="수정 결과")
    updated: bool = Field(default=True, description="수정 성공 여부")
