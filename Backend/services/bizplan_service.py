from ninja.errors import HttpError

from core.llm_client import bizplan_coach, evaluate_business_plan, generate_business_plan


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
