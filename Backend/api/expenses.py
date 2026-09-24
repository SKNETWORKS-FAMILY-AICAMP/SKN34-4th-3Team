import base64

from datetime import date

from django.http import HttpResponse
from ninja import Router, File, Path, Query
from ninja.errors import HttpError
from ninja.files import UploadedFile

from api.deps import user_auth
from schemas.expenses import (
    DeductibilityResponse,
    ExpenseAnalysisResponse,
    ExpenseCategoryUpdate,
    ExpenseItemCreate,
    ExpenseListResponse,
    ExpenseVendorUpdate,
    ReceiptCreateResponse,
    ReceiptExtractionResponse,
)
from services import expense_service

router = Router(tags=["지출"], auth=user_auth)

MAX_RECEIPT_BYTES = 4 * 1024 * 1024


def _sniff_image_media_type(content: bytes) -> str | None:
    """업로드된 바이트에서 실제 이미지 형식을 읽어 낸다.

    Content-Type 헤더는 업로드하는 쪽이 원하는 값으로 마음대로 채울 수 있어(예: 실제로는
    HTML·스크립트인 파일에 "image/jpeg"를 붙여 보낼 수 있다), 저장·조회 응답에 그 값을
    그대로 쓰면 나중에 이 영수증 이미지를 열어 볼 때 브라우저가 그 값을 그대로 믿게
    된다. 그래서 헤더는 무시하고 파일 내용 앞부분(매직 바이트)으로 형식을 직접 판별한다.
    """
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/receipts", response=ReceiptCreateResponse, summary="영수증 등록")
def upload_receipt(
    request,
    image: UploadedFile = File(..., description="영수증 이미지 파일"),
):
    """이미지 바이트를 LLM Vision OCR로 보내고, 실패 시 파일명 규칙으로 추출합니다."""
    filename = image.name or "receipt.jpg"
    content = image.read()
    if len(content) > MAX_RECEIPT_BYTES:
        raise HttpError(413, "영수증 이미지는 4MB 이하여야 합니다.")
    mime_type = _sniff_image_media_type(content)
    if mime_type is None:
        raise HttpError(415, "영수증 이미지는 JPEG, PNG, WebP만 지원합니다.")
    image_b64 = base64.b64encode(content).decode("ascii") if content else None
    return expense_service.create_receipt(
        request.auth["id"],
        filename,
        image_base64=image_b64,
        mime_type=mime_type,
        image_bytes=content or None,
    )


@router.get("/receipts/{receipt_id}/image", summary="영수증 원본 이미지")
def receipt_image(
    request,
    receipt_id: int = Path(description="영수증 ID"),
):
    """업로드 당시 원본 이미지를 그대로 돌려준다. 나중에 어떤 영수증을 올렸는지 다시 확인할 때 쓴다."""
    data, mime_type = expense_service.get_receipt_image(receipt_id, request.auth["id"])
    return HttpResponse(content=data, content_type=mime_type)


@router.get(
    "/receipts/{receipt_id}",
    response=ReceiptExtractionResponse,
    summary="영수증 추출 결과 조회",
)
def receipt_detail(
    request,
    receipt_id: int = Path(description="영수증 ID"),
):
    return expense_service.get_extraction(receipt_id, request.auth["id"])


@router.get("", response=ExpenseListResponse, summary="지출 내역 조회")
def expense_list(
    request,
    category: str | None = Query(default=None, description="지출 카테고리 필터(선택)"),
    from_date: date | None = Query(default=None, alias="from", description="시작일"),
    to_date: date | None = Query(default=None, alias="to", description="종료일"),
):
    return {
        "expenses": expense_service.list_expenses(
            request.auth["id"],
            category,
            from_date=from_date,
            to_date=to_date,
        )
    }


@router.patch("/{expense_id}", response=DeductibilityResponse, summary="지출 분류 수정")
def update_expense(
    request,
    body: ExpenseCategoryUpdate,
    expense_id: int = Path(description="지출 ID"),
):
    return expense_service.update_category(expense_id, request.auth["id"], body.category)


@router.delete("/{expense_id}", summary="지출·영수증 삭제")
def delete_expense(
    request,
    expense_id: int = Path(description="지출 ID"),
):
    expense_service.delete_expense(expense_id, request.auth["id"])
    return {"deleted": True}


@router.get(
    "/{expense_id}/analysis",
    response=ExpenseAnalysisResponse,
    summary="영수증 판독·판단 과정",
)
def analysis(
    request,
    expense_id: int = Path(description="지출 ID"),
):
    """OCR이 읽은 항목과 판정에 이르는 단계를 돌려준다. LLM을 부르지 않아 즉시 응답한다."""
    return expense_service.analysis(expense_id, request.auth["id"])


@router.post(
    "/{expense_id}/items",
    response=ExpenseAnalysisResponse,
    summary="OCR이 놓친 품목 추가",
)
def add_item(
    request,
    body: ExpenseItemCreate,
    expense_id: int = Path(description="지출 ID"),
):
    """OCR이 읽지 못한 품목을 사용자가 직접 추가하고, 갱신된 판독 결과를 돌려줍니다."""
    return expense_service.add_item(expense_id, request.auth["id"], body.name, body.price)


@router.delete(
    "/{expense_id}/items/{item_index}",
    response=ExpenseAnalysisResponse,
    summary="품목 삭제",
)
def delete_item(
    request,
    expense_id: int = Path(description="지출 ID"),
    item_index: int = Path(description="화면에 보이는 품목 순서(0부터 시작)"),
):
    """품목을 지우고, 갱신된 판독 결과를 돌려줍니다."""
    return expense_service.delete_item(expense_id, request.auth["id"], item_index)


@router.patch(
    "/{expense_id}/vendor",
    response=ExpenseAnalysisResponse,
    summary="상호 수정",
)
def update_vendor(
    request,
    body: ExpenseVendorUpdate,
    expense_id: int = Path(description="지출 ID"),
):
    """OCR이 잘못 읽었거나 놓친 상호를 사용자가 직접 고치고, 갱신된 판독 결과를 돌려줍니다."""
    return expense_service.update_vendor(expense_id, request.auth["id"], body.vendor)


@router.get(
    "/{expense_id}/deductibility",
    response=DeductibilityResponse,
    summary="경비처리 가능성 조회",
)
def deductibility(
    request,
    expense_id: int = Path(description="지출 ID"),
):
    """규칙 판정에 LLM/RAG 근거 설명을 붙입니다."""
    return expense_service.deductibility(expense_id, request.auth["id"])
