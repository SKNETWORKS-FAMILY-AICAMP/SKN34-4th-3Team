from __future__ import annotations

from datetime import date as Date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ProofType = Literal["tax_invoice", "card_receipt", "cash_receipt", "simple_receipt", "unknown"]
DeductibilityTier = Literal["high", "ambiguous", "low"]


class ReceiptCreateResponse(BaseModel):
    model_config = ConfigDict(title="영수증 등록 결과")
    receiptId: int = Field(description="영수증 ID")
    status: str = Field(description="처리 상태")
    ocrSource: str = Field(default="mock", description="추출 출처: llm / heuristic / mock")
    proofType: ProofType = Field(default="unknown", description="인식된 증빙 유형")
    proofTypeLabel: str = Field(default="확인 불가", description="증빙 유형 한글 표기")


class ReceiptExtractionResponse(BaseModel):
    model_config = ConfigDict(title="영수증 추출 결과")
    date: Date = Field(description="거래일")
    vendor: str = Field(description="상호")
    amount: int = Field(description="금액")
    items: list[str] = Field(description="품목")
    proofType: ProofType = Field(default="unknown", description="인식된 증빙 유형")
    proofTypeLabel: str = Field(default="확인 불가", description="증빙 유형 한글 표기")
    ocrSource: str = Field(default="mock", description="추출 출처")


class ExpenseItem(BaseModel):
    model_config = ConfigDict(title="지출 항목")
    expenseId: int = Field(description="지출 ID")
    receiptId: int = Field(description="영수증 ID")
    vendor: str = Field(default="상호 미상", description="상호")
    category: str = Field(description="분류")
    amount: int = Field(description="금액")
    date: Date = Field(description="날짜")
    uploadedAt: datetime | None = Field(default=None, description="영수증을 올린 시각 (UTC)")
    deductible: bool = Field(description="경비 인정 가능 여부")
    tier: DeductibilityTier = Field(description="경비 인정 판정: high/ambiguous/low")
    tierLabel: str = Field(description="판정 한글 표기: 높음/애매함/어려움")
    proofType: ProofType = Field(default="unknown", description="인식된 증빙 유형")
    proofTypeLabel: str = Field(default="확인 불가", description="증빙 유형 한글 표기")
    proofValid: bool | None = Field(default=None, description="증빙 적격 여부 (None=판단 불가)")
    missingFields: list[str] = Field(default_factory=list, description="빠진 정보 목록")
    items: list[str] = Field(default_factory=list, description="품목")


class ExpenseListResponse(BaseModel):
    model_config = ConfigDict(title="지출 목록")
    expenses: list[ExpenseItem] = Field(description="지출들")


class AnalysisField(BaseModel):
    model_config = ConfigDict(title="OCR 인식 항목")
    key: str = Field(description="vendor / date / amount / items / proof")
    label: str = Field(description="항목 이름")
    value: str | None = Field(default=None, description="읽은 값. 못 읽었으면 None")
    read: bool | None = Field(default=None, description="실제로 읽었는지. None=기록 이전 영수증이라 알 수 없음")
    evidence: str | None = Field(default=None, description="영수증에 인쇄된 원문 근거")


class AnalysisStep(BaseModel):
    model_config = ConfigDict(title="판단 단계")
    key: str
    title: str = Field(description="단계 이름")
    result: Literal["pass", "warn", "fail", "unknown"] = Field(description="단계 결과")
    detail: str = Field(description="이 단계에서 무엇을 보고 어떻게 판단했는지")


class LawRef(BaseModel):
    model_config = ConfigDict(title="관련 법령")
    law: str = Field(description="법령명")
    article: str = Field(description="조문 번호")
    title: str = Field(description="조문 제목")
    point: str = Field(description="이 지출과 관련된 요지(요약)")
    who: str | None = Field(default=None, description="적용 대상: 개인사업자 / 법인 / 복식부기의무자")
    url: str = Field(description="국가법령정보센터 원문 링크")


class ExpenseAnalysisResponse(BaseModel):
    model_config = ConfigDict(title="영수증 판독·판단 과정")
    fields: list[AnalysisField]
    steps: list[AnalysisStep]
    laws: list[LawRef] = Field(default_factory=list, description="관련 법령")
    lawNote: str | None = Field(default=None, description="개별 조문이 없는 항목의 안내")
    tier: DeductibilityTier
    tierLabel: str
    ocrSource: str = Field(description="ocr_llm / vision / mock / legacy")
    ocrConfidence: float | None = Field(default=None, description="OCR 인식 신뢰도 평균(%). ocr_llm일 때만 값이 있음")


class ExpenseCategoryUpdate(BaseModel):
    model_config = ConfigDict(title="지출 분류 수정")
    category: str = Field(description="사무용품 / 통신비 / 차량유지비 / 광고선전비 / 임차료 / 복리후생비 / 접대비 / 교육·도서 / 기타")


class DeductibilityResponse(BaseModel):
    model_config = ConfigDict(title="경비처리 가능성")
    deductible: bool = Field(description="인정 가능 여부")
    confidence: float = Field(description="신뢰도 (0~1)")
    basis: str = Field(description="안내 문구")
    llmUsed: bool = Field(default=False, description="RAG/LLM 설명 여부")
    sources: list[str] = Field(default_factory=list, description="근거 문서 제목")
    tier: DeductibilityTier = Field(description="경비 인정 판정: high/ambiguous/low")
    tierLabel: str = Field(description="판정 한글 표기: 높음/애매함/어려움")
    proofType: ProofType = Field(default="unknown", description="인식된 증빙 유형")
    proofTypeLabel: str = Field(default="확인 불가", description="증빙 유형 한글 표기")
    proofValid: bool | None = Field(default=None, description="증빙 적격 여부 (None=판단 불가)")
    missingFields: list[str] = Field(default_factory=list, description="빠진 정보 목록")
