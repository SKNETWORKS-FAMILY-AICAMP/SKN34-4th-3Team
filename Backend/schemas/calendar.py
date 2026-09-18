from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class CalendarEvent(BaseModel):
    model_config = ConfigDict(title="캘린더 일정")
    id: int = Field(description="일정 ID")
    eventType: str = Field(description="종류: TAX, POLICY, USER")
    title: str = Field(description="일정 제목")
    dueDate: date = Field(description="마감일")
    description: str = Field(description="설명")
    policyId: int | None = Field(default=None, description="지원정책 ID (지원금 일정일 때)")
    mine: bool = Field(default=False, description="내가 등록한 개인 일정인지")


class CalendarCreateRequest(BaseModel):
    model_config = ConfigDict(title="개인 일정 등록")
    title: str = Field(min_length=1, description="일정 제목")
    dueDate: date = Field(description="날짜")
    description: str = Field(default="", description="메모")
    remind: bool = Field(default=True, description="같은 날 리마인더도 만들지")
    notifyAt: datetime | None = Field(default=None, description="알림 시각")


class CalendarCreateResponse(BaseModel):
    model_config = ConfigDict(title="개인 일정 등록 결과")
    event: CalendarEvent


class CalendarResponse(BaseModel):
    model_config = ConfigDict(title="캘린더 응답")
    events: list[CalendarEvent] = Field(description="일정 목록")


class ReminderItem(BaseModel):
    model_config = ConfigDict(title="리마인더")
    reminderId: int = Field(description="리마인더 ID")
    eventId: int = Field(description="일정 ID")
    title: str = Field(description="일정 제목")
    dueDate: date = Field(description="마감일")
    notifyAt: datetime = Field(description="알림 시각")
    dueSoon: bool = Field(default=False, description="마감 3일 이내")
    arrived: bool = Field(default=False, description="알림 시각이 지났는지(앱 내 알림)")


class ReminderListResponse(BaseModel):
    model_config = ConfigDict(title="리마인더 목록")
    reminders: list[ReminderItem] = Field(description="리마인더들")


class ReminderCreateRequest(BaseModel):
    model_config = ConfigDict(title="리마인더 등록")
    eventId: int = Field(description="일정 ID")
    notifyAt: datetime = Field(description="알림 시각")


class ReminderCreateResponse(BaseModel):
    model_config = ConfigDict(title="리마인더 등록 결과")
    reminderId: int = Field(description="생성된 리마인더 ID")
