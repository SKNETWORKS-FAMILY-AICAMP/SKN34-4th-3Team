import base64

from ninja.errors import HttpError

from core.llm_client import (
    bizplan_coach,
    evaluate_business_plan,
    extract_business_plan_template,
    generate_business_plan,
)

MAX_TEMPLATE_FILE_BYTES = 4 * 1024 * 1024


def generate(body: dict) -> dict:
    """입력한 사업 정보로 PSST 사업계획서 초안을 만든다. LLM이 꺼져 있으면 503."""
    result = generate_business_plan(body)
    if not result:
        raise HttpError(503, "지금은 사업계획서 초안을 만들 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def evaluate(body: dict) -> dict:
    """작성된 PSST 초안에 AI 예비진단(자체 채점)을 매긴다. LLM이 꺼져 있으면 503."""
    result = evaluate_business_plan(body)
    if not result:
        raise HttpError(503, "지금은 예비진단을 실행할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def coach(body: dict) -> dict:
    """아이디어 어시스턴트에게 질문하고 답을 받는다. LLM이 꺼져 있으면 503."""
    result = bizplan_coach(body)
    if not result:
        raise HttpError(503, "지금은 어시스턴트를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    return result


def extract_template_file(filename: str, content: bytes, mime_type: str) -> dict:
    """지원사업 공고 첨부 PDF 양식에서 텍스트를 추출한다. LLM을 부르지 않아 즉시 처리된다."""
    if mime_type != "application/pdf":
        raise HttpError(415, "PDF 파일만 올릴 수 있습니다.")
    if len(content) > MAX_TEMPLATE_FILE_BYTES:
        raise HttpError(413, "양식 파일은 4MB 이하여야 합니다.")
    file_base64 = base64.b64encode(content).decode("ascii")
    result = extract_business_plan_template(filename, file_base64, mime_type)
    if not result:
        raise HttpError(422, "양식 PDF에서 글자를 읽지 못했습니다. 다른 파일로 시도해 주세요.")
    return result
