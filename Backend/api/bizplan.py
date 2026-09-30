from django.http import HttpResponse
from django.utils.http import content_disposition_header
from ninja import Router

from api.deps import user_auth
from schemas.bizplan import (
    BizplanCoachRequest,
    BizplanCoachResponse,
    BizplanDocumentDeleteResponse,
    BizplanDocumentItem,
    BizplanDocumentListResponse,
    BizplanDraftResponse,
    BizplanDraftSave,
    BusinessPlanEvaluateRequest,
    BusinessPlanEvaluateResponse,
    BusinessPlanRefineRequest,
    BusinessPlanRefineResponse,
    BusinessPlanRenderRequest,
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


@router.post("/documents", response=BizplanDocumentItem, summary="사업계획서 파일 저장")
def save_document(request, body: BusinessPlanRenderRequest):
    """서버에서 렌더링한 파일을 보관합니다. 사용자당 8개, 파일당 50MiB 이하입니다."""
    return bizplan_service.save_document(request.auth["id"], body.model_dump())


@router.get("/documents", response=BizplanDocumentListResponse, summary="내 사업계획서 서류 목록")
def documents(request):
    return bizplan_service.list_documents(request.auth["id"])


@router.get("/documents/{document_id}/file", summary="사업계획서 원본 다운로드")
def document_file(request, document_id: int):
    data, mime_type, file_name = bizplan_service.get_document_file(request.auth["id"], document_id)
    response = HttpResponse(content=data, content_type=mime_type)
    response["Content-Disposition"] = content_disposition_header(True, file_name)
    return response


@router.delete("/documents/{document_id}", response=BizplanDocumentDeleteResponse, summary="사업계획서 서류 삭제")
def delete_document(request, document_id: int):
    bizplan_service.delete_document(request.auth["id"], document_id)
    return {"deleted": True}
