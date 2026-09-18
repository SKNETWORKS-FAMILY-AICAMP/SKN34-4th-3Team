"""LLM Prompt에 전달할 완료 대화 이력을 작게 유지한다."""


PROMPT_HISTORY_MAX_MESSAGES = 10
PROMPT_HISTORY_MAX_CHARACTERS = 4000


def compact_conversation_history(
    history: list[dict[str, str]],
    *,
    max_messages: int = PROMPT_HISTORY_MAX_MESSAGES,
    max_characters: int = PROMPT_HISTORY_MAX_CHARACTERS,
) -> list[dict[str, str]]:
    """최근 완료 쌍을 메시지 수와 전체 글자 수 제한 안에 보존한다."""
    completed_message_count = len(history) - (len(history) % 2)
    recent = [
        {
            "role": str(message.get("role", "")),
            "content": str(message.get("content", "")),
        }
        for message in history[:completed_message_count][-max_messages:]
    ]
    while recent and sum(len(message["content"]) for message in recent) > (
        max_characters
    ):
        del recent[:2]
    return recent
