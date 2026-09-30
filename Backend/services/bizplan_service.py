import base64
import binascii
import json
from concurrent.futures import ThreadPoolExecutor
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
# 임시저장에는 양식(4 MiB)과 이미지(합계 4 MiB)가 Base64로 들어가 최대 약 10.7 MB가 된다.
MAX_DRAFT_BYTES = 12 * 1024 * 1024
MAX_DOCUMENTS_PER_USER = 8
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
DOCUMENT_LIMIT_MESSAGE = (
    "서류는 8개까지 저장할 수 있습니다. "
    "마이페이지 서류 탭에서 삭제한 뒤 다시 시도해 주세요."
)


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


def get_draft(user_id: int) -> dict:
    row = repo.get_bizplan_draft(user_id)
    if not row:
        return {"data": None, "updatedAt": None}
    return {"data": row.get("data") or {}, "updatedAt": row.get("updated_at")}


def _check_size(data: dict) -> None:
    size = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if size > MAX_DRAFT_BYTES:
        raise HttpError(413, "임시저장 내용은 12 MiB 이하여야 합니다. 첨부 파일을 줄여 주세요.")


def save_draft(user_id: int, data: dict) -> None:
    _check_size(data)
    repo.upsert_bizplan_draft(user_id, data)


def delete_draft(user_id: int) -> None:
    repo.delete_bizplan_draft(user_id)


def _document_item(row: dict) -> dict:
    files = [row, *(row.get("files") or [])]
    return {
        "id": row["id"], "title": row["title"], "fileName": row["file_name"],
        "format": row["format"], "sizeBytes": row["size_bytes"],
        "createdAt": row["created_at"],
        "files": [
            {"format": file["format"], "fileName": file["file_name"], "sizeBytes": file["size_bytes"]}
            for file in sorted(files, key=lambda file: file["format"])
        ],
    }


def save_document(user_id: int, body: dict) -> dict:
    if repo.count_bizplan_documents(user_id) >= MAX_DOCUMENTS_PER_USER:
        raise HttpError(409, DOCUMENT_LIMIT_MESSAGE)
    template = body.get("template")
    if template:
        _validate_template_file(template)
        formats = [Path(template["fileName"]).suffix.lower().lstrip(".")]
    else:
        primary_format = body.get("format", "hwpx")
        formats = [primary_format, "pdf" if primary_format == "hwpx" else "hwpx"]
    # 형식별 렌더를 동시에 실행해 최악 대기 시간을 렌더 1회(LLM_TIMEOUT_BIZPLAN) 수준으로 맞춘다.
    with ThreadPoolExecutor(max_workers=len(formats)) as executor:
        rendered_files = list(executor.map(lambda format: render({**body, "format": format}), formats))
    files = [_decode_document_file(rendered, format) for rendered, format in zip(rendered_files, formats)]
    primary, *additional = files
    row = repo.insert_bizplan_document(
        user_id, body["title"], primary["file_name"], primary["format"],
        primary["mime_type"], primary["file_data"], MAX_DOCUMENTS_PER_USER,
        additional_files=additional,
    )
    if row is None:
        raise HttpError(409, DOCUMENT_LIMIT_MESSAGE)
    return _document_item(row)


def _decode_document_file(rendered: dict, format: str) -> dict:
    try:
        raw = base64.b64decode(rendered["contentBase64"], validate=True)
    except (binascii.Error, ValueError, TypeError, KeyError) as exc:
        raise HttpError(503, "생성된 파일 데이터가 올바르지 않습니다.") from exc
    if not raw:
        raise HttpError(503, "생성된 파일이 비어 있습니다.")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise HttpError(413, "파일이 50MiB를 넘어 저장하지 못했습니다.")
    return {
        "format": format, "file_name": rendered["fileName"], "mime_type": rendered["mimeType"],
        "file_data": raw, "size_bytes": len(raw),
    }


def list_documents(user_id: int) -> dict:
    draft = repo.get_bizplan_draft_summary(user_id)
    return {
        "draft": {
            "title": (draft["title"] or "").strip() or "사업계획서",
            "updatedAt": draft["updated_at"],
        } if draft else None,
        "documents": [_document_item(row) for row in repo.list_bizplan_documents(user_id)],
    }


def get_document_file(user_id: int, document_id: int, format: str | None = None) -> tuple[bytes, str, str]:
    row = repo.get_bizplan_document(user_id, document_id, format)
    if row is None:
        raise HttpError(404, "서류를 찾을 수 없습니다.")
    return bytes(row["file_data"]), row["mime_type"], row["file_name"]


def delete_document(user_id: int, document_id: int) -> None:
    if not repo.delete_bizplan_document(user_id, document_id):
        raise HttpError(404, "서류를 찾을 수 없습니다.")


# ---- 사업계획서 보관함(마이페이지 관리) ----
UNTITLED_PLAN = "제목 없는 사업계획서"
PLAN_STATUS_LABELS = {
    "writing": "작성 중",
    "drafted": "초안 완성",
    "evaluated": "평가 완료",
    "done": "최종 완성",
}


def _has_content(data: dict) -> bool:
    form = data.get("form") or {}
    return bool(data.get("plan") or any(str(v).strip() for v in form.values() if v))


def plan_meta(data: dict) -> tuple[str, str, int | None]:
    """목록에 보여줄 제목·진행 단계·점수를 작성 화면 상태에서 뽑는다."""
    form = data.get("form") or {}
    title = str(form.get("businessName") or "").strip()[:200] or UNTITLED_PLAN
    if data.get("finalPlan"):
        status = "done"
    elif data.get("evalResult"):
        status = "evaluated"
    elif data.get("plan"):
        status = "drafted"
    else:
        status = "writing"
    score = None
    for key in ("finalEvalResult", "evalResult"):
        value = (data.get(key) or {}).get("overallScore")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            score = int(value)
            break
    return title, status, score


def _owned_plan(user_id: int, plan_id: int) -> dict:
    row = repo.get_bizplan(plan_id)
    if not row or row["user_id"] != user_id:
        raise HttpError(404, "사업계획서를 찾을 수 없습니다.")
    return row


def _import_legacy_draft(user_id: int) -> None:
    """보관함이 생기기 전의 임시저장(planId 없음)을 보관함 한 건으로 옮기고 작성 화면을 그 건에 연결한다."""
    draft = repo.get_bizplan_draft(user_id)
    data = (draft or {}).get("data") or {}
    if not data or data.get("planId") or not _has_content(data):
        return
    title, status, score = plan_meta(data)
    plan_id = repo.insert_bizplan(user_id, title, status, score, data)
    repo.upsert_bizplan_draft(user_id, {**data, "planId": plan_id})


def list_plans(user_id: int) -> dict:
    _import_legacy_draft(user_id)
    draft = repo.get_bizplan_draft(user_id)
    current_id = ((draft or {}).get("data") or {}).get("planId")
    return {
        "plans": [
            {
                "id": row["id"],
                "title": row["title"] or UNTITLED_PLAN,
                "status": row["status"],
                "statusLabel": PLAN_STATUS_LABELS.get(row["status"], row["status"]),
                "score": row["score"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "isCurrent": row["id"] == current_id,
            }
            for row in repo.list_bizplans(user_id)
        ]
    }


def save_plan(user_id: int, plan_id: int | None, data: dict) -> dict:
    """작성 화면 상태를 보관함에 저장한다. plan_id가 없으면 새로 만들고 그 ID를 돌려준다."""
    _check_size(data)
    data = {k: v for k, v in data.items() if k != "planId"}
    title, status, score = plan_meta(data)
    if plan_id is None:
        return {"id": repo.insert_bizplan(user_id, title, status, score, data)}
    _owned_plan(user_id, plan_id)
    repo.update_bizplan(plan_id, title, status, score, data)
    return {"id": plan_id}


def rename_plan(user_id: int, plan_id: int, title: str) -> None:
    _owned_plan(user_id, plan_id)
    repo.rename_bizplan(plan_id, title.strip()[:200] or UNTITLED_PLAN)


def delete_plan(user_id: int, plan_id: int) -> None:
    _owned_plan(user_id, plan_id)
    repo.delete_bizplan(plan_id)
    # 지운 건이 작성 화면에 열려 있으면 작성 화면도 비운다(지운 건이 다시 저장되지 않게).
    # 빈 값으로 덮지 않고 행을 지워야 서류 탭에 빈 '임시저장' 항목이 남지 않는다.
    draft = repo.get_bizplan_draft(user_id)
    if ((draft or {}).get("data") or {}).get("planId") == plan_id:
        repo.delete_bizplan_draft(user_id)


def open_plan(user_id: int, plan_id: int) -> None:
    """보관한 사업계획서를 작성 화면으로 불러온다(작성 화면 임시저장을 그 건으로 바꾼다)."""
    row = _owned_plan(user_id, plan_id)
    repo.upsert_bizplan_draft(user_id, {**(row.get("data") or {}), "planId": plan_id})


def new_plan(user_id: int) -> None:
    """작성 화면을 비워 새 사업계획서를 시작한다. 지금 열린 건은 보관함에 그대로 남는다."""
    repo.delete_bizplan_draft(user_id)
