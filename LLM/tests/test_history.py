from src.rag.history import compact_conversation_history


def test_history_keeps_latest_five_complete_pairs() -> None:
    history = [
        message
        for index in range(7)
        for message in (
            {"role": "user", "content": f"질문-{index}"},
            {"role": "assistant", "content": f"답변-{index}"},
        )
    ]

    compacted = compact_conversation_history(history)

    assert len(compacted) == 10
    assert compacted[0]["content"] == "질문-2"
    assert compacted[-1]["content"] == "답변-6"


def test_history_drops_oldest_pairs_until_under_character_limit() -> None:
    history = [
        message
        for index in range(3)
        for message in (
            {"role": "user", "content": f"질문-{index}-" + "가" * 1000},
            {"role": "assistant", "content": f"답변-{index}-" + "나" * 1000},
        )
    ]

    compacted = compact_conversation_history(history)

    assert len(compacted) == 2
    assert compacted[0]["content"].startswith("질문-2-")
    assert sum(len(message["content"]) for message in compacted) <= 4000
