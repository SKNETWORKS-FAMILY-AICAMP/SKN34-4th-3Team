from typing import Literal

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from ninja import Path, Router

from api.deps import user_auth
from schemas.bizplan import (
    BizplanCoachRequest,
    BizplanCoachResponse,
    BizplanDocumentDeleteResponse,
    BizplanDocumentItem,
    BizplanDocumentListResponse,
    BizplanDraftResponse,
    BizplanDraftSave,
    BizplanListResponse,
    BizplanRenameRequest,
    BizplanSaveRequest,
    BizplanSaveResponse,
    BusinessPlanEvaluateRequest,
    BusinessPlanEvaluateResponse,
    BusinessPlanRefineRequest,
    BusinessPlanRefineResponse,
    BusinessPlanRenderRequest,
    BusinessPlanDocumentSaveRequest,
    BusinessPlanRenderResponse,
    BusinessPlanRequest,
    BusinessPlanResponse,
    BusinessPlanTemplateRequest,
    BusinessPlanTemplateResponse,
)
from schemas.users import UpdatedResponse
from services import bizplan_service

router = Router(tags=["사업계획서"], auth=user_auth)


@router.post("/generate", response=BusinessPlanResponse, summary="사업계획서 초안 생성")
def generate(request, body: BusinessPlanRequest):
    """사업 정보와 선택 공고·양식 또는 사용자가 보완한 항목으로 초안을 만듭니다."""
    return bizplan_service.generate(body.model_dump(), request.auth["id"])


@router.post("/refine", response=BusinessPlanRefineResponse, summary="사업계획서 입력 정리")
def refine(request, body: BusinessPlanRefineRequest):
    """입력된 사실을 추가하거나 삭제하지 않고 읽기 쉬운 문장으로 정리합니다."""
    return bizplan_service.refine(body.model_dump())


@router.post(
    "/template-inspect",
    response=BusinessPlanTemplateResponse,
    summary="사업계획서 양식 검사",
)
def template_inspect(request, body: BusinessPlanTemplateRequest):
    """PDF/HWPX 양식의 입력 위치와 출력 가능 형식을 검사합니다."""
    return bizplan_service.inspect_template(body.model_dump())


@router.post("/evaluate", response=BusinessPlanEvaluateResponse, summary="AI 예비진단(자체 채점)")
def evaluate(request, body: BusinessPlanEvaluateRequest):
    """작성된 초안에 공고·양식 기준을 반영한 점수와 보완점을 제공합니다."""
    return bizplan_service.evaluate(body.model_dump())


@router.post("/render", response=BusinessPlanRenderResponse, summary="사업계획서 파일 출력")
def render(request, body: BusinessPlanRenderRequest):
    """기본 또는 제출 양식으로 HWPX/PDF 파일을 생성합니다."""
    return bizplan_service.render(body.model_dump())


@router.post("/coach", response=BizplanCoachResponse, summary="아이디어 어시스턴트")
def coach(request, body: BizplanCoachRequest):
    """작성 중인 사업계획서 내용을 참고해 아이디어 구체화를 돕습니다. 대화 기록은 저장하지 않습니다."""
    return bizplan_service.coach(body.model_dump())


@router.get("/draft", response=BizplanDraftResponse, summary="사업계획서 임시저장 조회")
def draft(request):
    """로그인한 사용자의 임시저장 초안을 반환합니다. 없으면 data가 null입니다."""
    return bizplan_service.get_draft(request.auth["id"])


@router.put("/draft", response=UpdatedResponse, summary="사업계획서 임시저장")
def save_draft(request, body: BizplanDraftSave):
    """작성 화면 상태를 유저당 1건으로 덮어써 저장합니다."""
    bizplan_service.save_draft(request.auth["id"], body.data)
    return {"updated": True}


@router.delete("/draft", response=BizplanDocumentDeleteResponse, summary="사업계획서 임시저장 삭제")
def delete_draft(request):
    bizplan_service.delete_draft(request.auth["id"])
    return {"deleted": True}


@router.post("/documents", response=BizplanDocumentItem, summary="사업계획서 파일 저장")
def save_document(request, body: BusinessPlanDocumentSaveRequest):
    """기본 문서는 PDF·HWPX를 함께, 제출 양식은 원본 형식을 보관합니다. 최대 8문서입니다."""
    return bizplan_service.save_document(request.auth["id"], body.model_dump())


@router.get("/documents", response=BizplanDocumentListResponse, summary="내 사업계획서 서류 목록")
def documents(request):
    return bizplan_service.list_documents(request.auth["id"])


@router.get("/documents/{document_id}/file", summary="사업계획서 원본 다운로드")
def document_file(request, document_id: int, format: Literal["pdf", "hwpx"] | None = None):
    data, mime_type, file_name = bizplan_service.get_document_file(request.auth["id"], document_id, format)
    response = HttpResponse(content=data, content_type=mime_type)
    response["Content-Disposition"] = content_disposition_header(True, file_name)
    return response


@router.delete("/documents/{document_id}", response=BizplanDocumentDeleteResponse, summary="사업계획서 서류 삭제")
def delete_document(request, document_id: int):
    bizplan_service.delete_document(request.auth["id"], document_id)
    return {"deleted": True}


@router.get("/plans", response=BizplanListResponse, summary="보관한 사업계획서 목록")
def plans(request):
    """마이페이지에서 관리할 사업계획서 목록을 최근 저장 순으로 반환합니다."""
    return bizplan_service.list_plans(request.auth["id"])


@router.post("/plans", response=BizplanSaveResponse, summary="사업계획서 새로 보관")
def create_plan(request, body: BizplanSaveRequest):
    """작성 화면 상태를 보관함에 새 건으로 저장하고 ID를 돌려줍니다."""
    return bizplan_service.save_plan(request.auth["id"], None, body.data)


# 경로에 숫자가 아닌 'new'가 먼저 걸리도록 {plan_id} 경로보다 앞에 둔다.
@router.post("/plans/new", response=UpdatedResponse, summary="새 사업계획서 시작")
def new_plan(request):
    """작성 화면을 비웁니다. 지금 열려 있던 사업계획서는 보관함에 남습니다."""
    bizplan_service.new_plan(request.auth["id"])
    return {"updated": True}


@router.put("/plans/{plan_id}", response=BizplanSaveResponse, summary="보관한 사업계획서 저장")
def save_plan(request, body: BizplanSaveRequest, plan_id: int = Path(description="사업계획서 ID")):
    """작성 화면 상태로 보관한 사업계획서를 덮어씁니다."""
    return bizplan_service.save_plan(request.auth["id"], plan_id, body.data)


@router.patch("/plans/{plan_id}", response=UpdatedResponse, summary="사업계획서 이름 변경")
def rename_plan(request, body: BizplanRenameRequest, plan_id: int = Path(description="사업계획서 ID")):
    """보관함에 보이는 제목을 바꿉니다."""
    bizplan_service.rename_plan(request.auth["id"], plan_id, body.title)
    return {"updated": True}


@router.delete("/plans/{plan_id}", response=UpdatedResponse, summary="보관한 사업계획서 삭제")
def delete_plan(request, plan_id: int = Path(description="사업계획서 ID")):
    """보관함에서 지웁니다. 작성 화면에 열려 있던 건이면 작성 화면도 비웁니다."""
    bizplan_service.delete_plan(request.auth["id"], plan_id)
    return {"updated": True}


@router.post("/plans/{plan_id}/open", response=UpdatedResponse, summary="보관한 사업계획서 열기")
def open_plan(request, plan_id: int = Path(description="사업계획서 ID")):
    """보관한 사업계획서를 작성 화면으로 불러옵니다(작성 화면 임시저장을 그 건으로 바꿈)."""
    bizplan_service.open_plan(request.auth["id"], plan_id)
    return {"updated": True}
