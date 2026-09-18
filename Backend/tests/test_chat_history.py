"""chat_service.send_message: 사용자별 대화 문맥 전달 계약."""

import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from services import chat_service

RAG_OK = {
    "answer": "LLM 답변",
    "sources": [{"title": "문서", "url": "http://x", "excerpt": "발췌"}],
    "grounded": True,
    "status": "success",
}


class FakeRepo:
    """chat_messages를 (user_id, category)별로 들고 있는 대역."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.inserted = []

    def recent_chats(self, user_id, category, limit=10):
        rows = [
            r for r in self.rows if r["user_id"] == user_id and r["category"] == category
        ]
        return rows[-limit:]

    def insert_chat(self, user_id, category, question, answer, sources):
        self.inserted.append((user_id, category, question, answer, sources))
        return 100 + len(self.inserted)

    def get_user(self, user_id):
        return {"id": user_id, "name": "김창업", "age": 30, "region": "서울"}

    def get_profile(self, user_id):
        return {"business_type": "개인", "industry": "IT"}

    def open_announcements(self):
        return []


def row(user_id, category, question, answer):
    return {
        "user_id": user_id,
        "category": category,
        "question": question,
        "answer": answer,
    }


class ConversationHistoryTest(unittest.TestCase):
    def send(
        self,
        repo,
        question="가족이 두 명이면?",
        category="tax",
        rag=RAG_OK,
        user_id=1,
        roadmap_step=None,
    ):
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer", return_value=rag
        ) as rag_answer:
            result = chat_service.send_message(
                user_id,
                category,
                question,
                roadmap_step=roadmap_step,
            )
        return result, rag_answer

    def history_of(self, rag_answer):
        return rag_answer.call_args[1]["conversation_history"]

    def test_other_user_rows_are_excluded(self):
        repo = FakeRepo(
            [
                row(1, "tax", "월급은 320만원이야", "A 답변"),
                row(2, "tax", "B 질문", "B 답변"),
            ]
        )
        _, rag_answer = self.send(repo, user_id=1)
        contents = [item["content"] for item in self.history_of(rag_answer)]
        self.assertIn("월급은 320만원이야", contents)
        self.assertNotIn("B 질문", contents)
        self.assertNotIn("B 답변", contents)

    def test_other_category_rows_are_excluded(self):
        repo = FakeRepo(
            [
                row(1, "tax", "세금 질문", "세금 답변"),
                row(1, "policy", "정책 질문", "정책 답변"),
            ]
        )
        _, rag_answer = self.send(repo, category="tax")
        contents = [item["content"] for item in self.history_of(rag_answer)]
        self.assertEqual(contents, ["세금 질문", "세금 답변"])

    def test_only_recent_ten_pairs_in_chronological_order(self):
        repo = FakeRepo([row(1, "tax", f"질문{i}", f"답변{i}") for i in range(12)])
        _, rag_answer = self.send(repo)
        history = self.history_of(rag_answer)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], {"role": "user", "content": "질문2"})
        self.assertEqual(history[1], {"role": "assistant", "content": "답변2"})
        self.assertEqual(history[-1], {"role": "assistant", "content": "답변11"})

    def test_roles_alternate_in_pairs(self):
        repo = FakeRepo([row(1, "tax", f"질문{i}", f"답변{i}") for i in range(3)])
        _, rag_answer = self.send(repo)
        roles = [item["role"] for item in self.history_of(rag_answer)]
        self.assertEqual(roles, ["user", "assistant"] * 3)

    def test_question_and_answer_are_clipped(self):
        repo = FakeRepo([row(1, "tax", "가" * 1500, "나" * 5000)])
        _, rag_answer = self.send(repo)
        history = self.history_of(rag_answer)
        self.assertEqual(len(history[0]["content"]), chat_service.HISTORY_QUESTION_LIMIT)
        self.assertEqual(len(history[1]["content"]), chat_service.HISTORY_ANSWER_LIMIT)

    def test_oldest_pairs_dropped_over_total_limit(self):
        # 한 쌍이 5,000자라 3쌍이면 15,000자로 12,000자를 넘는다.
        repo = FakeRepo(
            [row(1, "tax", f"질문{i}" + "가" * 994, "나" * 4000) for i in range(3)]
        )
        _, rag_answer = self.send(repo)
        history = self.history_of(rag_answer)
        self.assertEqual(len(history), 4)
        self.assertTrue(history[0]["content"].startswith("질문1"))
        total = sum(len(item["content"]) for item in history)
        self.assertLessEqual(total, chat_service.HISTORY_TOTAL_LIMIT)

    def test_incomplete_rows_are_skipped(self):
        repo = FakeRepo([row(1, "tax", "질문", ""), row(1, "tax", "질문2", "답변2")])
        _, rag_answer = self.send(repo)
        contents = [item["content"] for item in self.history_of(rag_answer)]
        self.assertEqual(contents, ["질문2", "답변2"])

    def test_failure_and_guardrail_answers_are_not_reused_as_context(self):
        repo = FakeRepo(
            [
                row(
                    1,
                    "roadmap",
                    "날씨 질문",
                    "창업 로드맵 단계와 준비 작업에 관한 질문만 답변할 수 있습니다.",
                ),
                row(
                    1,
                    "roadmap",
                    "연결 실패 질문",
                    chat_service.MOCK_ANSWERS["roadmap"],
                ),
                row(1, "roadmap", "정상 질문", "정상 답변"),
            ]
        )

        _, rag_answer = self.send(repo, category="roadmap")

        self.assertEqual(
            self.history_of(rag_answer),
            [
                {"role": "user", "content": "정상 질문"},
                {"role": "assistant", "content": "정상 답변"},
            ],
        )

    def test_first_question_sends_no_history(self):
        repo = FakeRepo()
        _, rag_answer = self.send(repo, question="첫 질문")
        kwargs = rag_answer.call_args[1]
        self.assertIsNone(kwargs["conversation_history"])
        self.assertEqual(rag_answer.call_args[0][0], "첫 질문")
        self.assertEqual(kwargs["category"], "tax")
        self.assertIsNotNone(kwargs["user_context"])

    def test_current_question_is_not_duplicated_and_is_saved(self):
        repo = FakeRepo([row(1, "tax", "월급은 320만원이야", "A 답변")])
        result, rag_answer = self.send(repo, question="가족이 두 명이면?")
        contents = [item["content"] for item in self.history_of(rag_answer)]
        self.assertNotIn("가족이 두 명이면?", contents)
        self.assertEqual(len(repo.inserted), 1)
        user_id, category, question, answer, _ = repo.inserted[0]
        self.assertEqual((user_id, category, question), (1, "tax", "가족이 두 명이면?"))
        self.assertEqual(answer, "LLM 답변")
        self.assertEqual(result["messageId"], 101)

    def test_roadmap_history_uses_smaller_limit_and_forwards_step(self):
        repo = FakeRepo(
            [row(1, "roadmap", f"질문{i}", f"답변{i}") for i in range(8)]
        )

        _, rag_answer = self.send(
            repo,
            category="roadmap",
            roadmap_step="D",
        )

        kwargs = rag_answer.call_args[1]
        self.assertEqual(len(kwargs["conversation_history"]), 10)
        self.assertEqual(
            kwargs["conversation_history"][0],
            {"role": "user", "content": "질문3"},
        )
        self.assertEqual(kwargs["roadmap_step"], "D")

    def test_roadmap_history_drops_oldest_pairs_over_four_thousand_chars(self):
        repo = FakeRepo(
            [
                row(1, "roadmap", f"질문{i}" + "가" * 996, "나" * 1000)
                for i in range(3)
            ]
        )

        _, rag_answer = self.send(repo, category="roadmap")
        history = self.history_of(rag_answer)

        self.assertEqual(len(history), 4)
        self.assertTrue(history[0]["content"].startswith("질문1"))
        self.assertLessEqual(
            sum(len(item["content"]) for item in history),
            chat_service.ROADMAP_HISTORY_TOTAL_LIMIT,
        )


class ExistingContractTest(unittest.TestCase):
    def test_success_response_contract(self):
        repo = FakeRepo([row(1, "tax", "질문", "답변")])
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer", return_value=RAG_OK
        ):
            result = chat_service.send_message(1, "tax", "질문2")
        self.assertEqual(result["answer"], "LLM 답변")
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["guardrailReason"])
        self.assertTrue(result["llmUsed"])
        self.assertTrue(result["grounded"])
        self.assertFalse(result["needsConfirmation"])

    def test_out_of_scope_guardrail_drops_sources(self):
        repo = FakeRepo()
        rag = dict(RAG_OK, status="no_result", guardrail_reason="out_of_scope")
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer", return_value=rag
        ):
            result = chat_service.send_message(1, "tax", "날씨 알려줘")
        self.assertEqual(result["guardrailReason"], "out_of_scope")
        self.assertFalse(result["grounded"])
        self.assertTrue(result["needsConfirmation"])
        self.assertEqual(repo.inserted[0][4], [])

    def test_mock_fallback_when_llm_unreachable(self):
        repo = FakeRepo([row(1, "tax", "질문", "답변")])
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer", return_value=None
        ):
            result = chat_service.send_message(1, "tax", "질문2")
        self.assertEqual(result["status"], "integration_unavailable")
        self.assertFalse(result["llmUsed"])
        self.assertTrue(result["needsConfirmation"])
        self.assertIn(chat_service.MOCK_ANSWERS["tax"], result["answer"])

    def test_unknown_category_is_rejected_before_db_access(self):
        repo = MagicMock()
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer"
        ) as rag_answer:
            with self.assertRaises(HTTPException):
                chat_service.send_message(1, "unknown", "질문")
        repo.recent_chats.assert_not_called()
        rag_answer.assert_not_called()

    def test_roadmap_connection_failure_returns_only_connection_message(self):
        repo = FakeRepo()
        with patch.object(chat_service, "repo", repo), patch.object(
            chat_service, "rag_answer", return_value=None
        ):
            result = chat_service.send_message(1, "roadmap", "다음 할 일은?")

        self.assertEqual(result["answer"], chat_service.MOCK_ANSWERS["roadmap"])
        self.assertNotIn("근거 문서", result["answer"])


if __name__ == "__main__":
    unittest.main()
