from pydantic import BaseModel, ConfigDict, Field


class SignupRequest(BaseModel):
    model_config = ConfigDict(title="회원가입 요청")
    email: str = Field(description="이메일")
    password: str = Field(min_length=4, description="비밀번호 (4자 이상)")
    name: str = Field(default="사용자", description="이름")


class LoginRequest(BaseModel):
    model_config = ConfigDict(title="로그인 요청")
    email: str = Field(description="이메일")
    password: str = Field(description="비밀번호")


class SignupResponse(BaseModel):
    model_config = ConfigDict(title="회원가입 응답")
    userId: int = Field(description="생성된 사용자 ID")


class LoginResponse(BaseModel):
    model_config = ConfigDict(title="로그인 응답")
    accessToken: str = Field(description="인증 토큰")
    userId: int = Field(description="사용자 ID")
    name: str = Field(description="이름")
    role: str = Field(default="user", description="역할 (user 또는 admin)")
