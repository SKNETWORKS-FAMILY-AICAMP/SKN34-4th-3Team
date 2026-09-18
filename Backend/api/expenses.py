import base64

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile

from api.deps import get_current_user
from schemas.expenses import (
    DeductibilityResponse,
    ExpenseCategoryUpdate,
    ExpenseListResponse,
    ReceiptCreateResponse,
    ReceiptExtractionResponse,
)
from services import expense_service

router = APIRouter(prefix="/expenses", tags=["지출"])

MAX_RECEIPT_BYTES = 4 * 1024 * 1024


@router.post("/receipts", response_model=ReceiptCreateResponse, summary="영수증 등록")
async def upload_receipt(
    image: UploadFile = File(..., description="영수증 이미지 파일"),
    current: dict = Depends(get_current_user),
):
    """이미지 바이트를 LLM Vision OCR로 보내고, 실패 시 파일명 규칙으로 추출합니다."""
    filename = image.filename or "receipt.jpg"
    content = await image.read()
    if len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(status_code=413, detail="영수증 이미지는 4MB 이하여야 합니다.")
    image_b64 = base64.b64encode(content).decode("ascii") if content else None
    return expense_service.create_receipt(
        current["id"],
        filename,
        image_base64=image_b64,
        mime_type=image.content_type or "image/jpeg",
    )


@router.get(
    "/receipts/{receipt_id}",
    response_model=ReceiptExtractionResponse,
    summary="영수증 추출 결과 조회",
)
def receipt_detail(
    receipt_id: int = Path(description="영수증 ID"),
    current: dict = Depends(get_current_user),
):
    return expense_service.get_extraction(receipt_id, current["id"])


@router.get("", response_model=ExpenseListResponse, summary="지출 내역 조회")
def expense_list(
    category: str | None = Query(default=None, description="지출 카테고리 필터(선택)"),
    from_date: date | None = Query(default=None, alias="from", description="시작일"),
    to_date: date | None = Query(default=None, alias="to", description="종료일"),
    current: dict = Depends(get_current_user),
):
    return {
        "expenses": expense_service.list_expenses(
            current["id"],
            category,
            from_date=from_date,
            to_date=to_date,
        )
    }


@router.patch("/{expense_id}", response_model=DeductibilityResponse, summary="지출 분류 수정")
def update_expense(
    body: ExpenseCategoryUpdate,
    expense_id: int = Path(description="지출 ID"),
    current: dict = Depends(get_current_user),
):
    return expense_service.update_category(expense_id, current["id"], body.category)


@router.delete("/{expense_id}", summary="지출·영수증 삭제")
def delete_expense(
    expense_id: int = Path(description="지출 ID"),
    current: dict = Depends(get_current_user),
):
    expense_service.delete_expense(expense_id, current["id"])
    return {"deleted": True}


@router.get(
    "/{expense_id}/deductibility",
    response_model=DeductibilityResponse,
    summary="경비처리 가능성 조회",
)
def deductibility(
    expense_id: int = Path(description="지출 ID"),
    current: dict = Depends(get_current_user),
):
    """규칙 판정에 LLM/RAG 근거 설명을 붙입니다."""
    return expense_service.deductibility(expense_id, current["id"])
