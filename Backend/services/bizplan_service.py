import base64
import binascii
from pathlib import Path

from ninja.errors import HttpError

from core import repo
from core.llm_client import (
    LLMRequestError,
    bizplan_coach,
    evaluate_business_plan,
    generate_business_plan,
    inspect_business_plan_template,
    refine_business_plan,
    render_business_plan,
)


MAX_TEMPLATE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024


def _announcement_context(announcement_id: int | None) -> tuple[str, str]:
    if announcement_id is None:
        return "", ""
    announcement = repo.get_announcement(announcement_id)
    if not announcement:
        raise HttpError(404, "선택한 공고를 찾을 수 없습니다.")
    policy = (
        repo.get_policy(announcement.get("policy_id"))
        if announcement.get("policy_id")
        else None
    )
    title = str((policy or {}).get("title") or "")
    criteria = str(announcement.get("raw_content") or "").strip()[:6000]
    return title, criteria


def _validate_template_file(template: dict) -> None:
    suffix = Path(str(template.get("fileName") or "")).suffix.lower()
    if suffix not in {".pdf", ".hwpx"}:
        raise HttpError(422, "PDF 또는 HWPX 양식만 제출할 수 있습니다.")
    try:
        raw = base64.b64decode(str(template.get("contentBase64") or ""), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HttpError(422, "양식 파일 데이터가 올바르지 않습니다.") from exc
    if not raw:
        raise HttpError(422, "양식 파일이 비어 있습니다.")
    if len(raw) > MAX_TEMPLATE_BYTES:
        raise HttpError(413, "양식 파일은 4 MiB 이하여야 합니다.")


def _call_document_api(call, body: dict) -> dict:
    try:
        return call(body)
    except LLMRequestError as exc:
        allowed = {400, 404, 413, 415, 422, 429, 503, 504}
        status = exc.status_code if exc.status_code in allowed else 503
        raise HttpError(status, exc.message) from exc


def generate(body: dict, user_id: int | None = None) -> dict:
    """입력한 사업 정보로 PSST 사업계획서 초안을 만든다. LLM이 꺼져 있으면 503."""
    payload = dict(body)
    if user_id is not None:
        payload["applicantName"] = (repo.get_user(user_id) or {}).get("name") or ""
    title, criteria = _announcement_context(payload.get("announcementId"))
    if title:
        payload["targetProgram"] = title
    payload["announcementCriteria"] = criteria
    result = generate_business_plan(payload)
    if not result:
        raise HttpError(503, "지금은 사업계획서 초안을 만들 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def evaluate(body: dict) -> dict:
    """작성된 PSST 초안에 AI 예비진단(자체 채점)을 매긴다. LLM이 꺼져 있으면 503."""
    _, criteria = _announcement_context(body.get("announcementId"))
    template_fields = body.get("templateFields") or []
    template_criteria = (
        "제출한 양식의 필수 작성 항목: " + ", ".join(template_fields)
        + ". 각 항목에 맞는 내용과 누락 여부를 평가하세요."
        if template_fields else
        "기본 PSST 사업계획서 양식의 13개 항목을 기준으로 내용의 충실도, "
        "항목 간 논리적 연결, 실현 가능성과 누락 여부를 평가하세요."
    )
    payload = {
        "sections": body.get("sections") or [],
        "announcementCriteria": criteria,
        "templateCriteria": template_criteria,
    }
    result = evaluate_business_plan(payload)
    if not result:
        raise HttpError(503, "지금은 예비진단을 실행할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def coach(body: dict) -> dict:
    """아이디어 어시스턴트에게 질문하고 답을 받는다. LLM이 꺼져 있으면 503."""
    result = bizplan_coach(body)
    if not result:
        raise HttpError(503, "지금은 어시스턴트를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def refine(body: dict) -> dict:
    return _call_document_api(refine_business_plan, body)


def inspect_template(body: dict) -> dict:
    _validate_template_file(body)
    return _call_document_api(inspect_business_plan_template, body)


def render(body: dict) -> dict:
    if body.get("template"):
        _validate_template_file(body["template"])
    images = body.get("images") or []
    if images and not body.get("template"):
        raise HttpError(422, "이미지를 배치할 PDF/HWPX 양식이 필요합니다.")
    section_keys = {section["key"] for section in body.get("sections") or []}
    total_bytes = 0
    seen_image_keys = set()
    for image in images:
        if image["key"] not in section_keys or image["key"] in seen_image_keys:
            raise HttpError(422, "이미지 입력 영역이 초안 항목과 일치하지 않습니다.")
        seen_image_keys.add(image["key"])
        try:
            raw = base64.b64decode(image["contentBase64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HttpError(422, "이미지 파일 데이터가 올바르지 않습니다.") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise HttpError(413, "이미지는 파일당 2 MiB 이하여야 합니다.")
        if not (raw.startswith(b"\x89PNG\r\n\x1a\n") if image["mimeType"] == "image/png"
                else raw.startswith(b"\xff\xd8\xff")):
            raise HttpError(422, "이미지 형식과 파일 내용이 일치하지 않습니다.")
        total_bytes += len(raw)
    if total_bytes > 4 * 1024 * 1024:
        raise HttpError(413, "첨부 이미지의 합계는 4 MiB 이하여야 합니다.")
    return _call_document_api(render_business_plan, body)
