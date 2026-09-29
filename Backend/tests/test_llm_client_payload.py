"""llm_client.rag_answer: conversationHistory 직렬화."""

import json
import unittest
from unittest.mock import patch

import httpx

from core import llm_client


class RagAnswerPayloadTest(unittest.TestCase):
    def _body(self, **kwargs) -> dict:
        with patch.object(llm_client, "_post", return_value={"answer": "ok"}) as post:
            llm_client.rag_answer("질문", category="tax", **kwargs)
        return post.call_args[0][1]

    def test_history_is_serialized_when_present(self):
        history = [
            {"role": "user", "content": "월급은 320만원이야"},
            {"role": "assistant", "content": "답변"},
        ]
        body = self._body(conversation_history=history)
        self.assertEqual(body["conversationHistory"], history)

    def test_field_is_omitted_without_history(self):
        self.assertNotIn("conversationHistory", self._body())
        self.assertNotIn("conversationHistory", self._body(conversation_history=[]))
        self.assertNotIn("conversationHistory", self._body(conversation_history=None))

    def test_roadmap_step_is_serialized_when_present(self):
        with patch.object(llm_client, "_post", return_value={}) as post:
            llm_client.rag_answer(
                "다음 할 일은?",
                category="roadmap",
                roadmap_step="C",
            )
        body = post.call_args[0][1]
        self.assertEqual(body["category"], "roadmap")
        self.assertEqual(body["roadmapStep"], "C")
        self.assertEqual(
            post.call_args[1]["timeout"],
            llm_client.LLM_TIMEOUT_CHAT_POLICY,
        )

    def test_existing_fields_are_unchanged(self):
        body = self._body(
            user_context={"userId": 1},
            notice_results=[{"announcementId": 2}],
            conversation_history=[{"role": "user", "content": "q"}],
        )
        self.assertEqual(body["category"], "tax")
        self.assertEqual(body["question"], "질문")
        self.assertEqual(body["userContext"], {"userId": 1})
        self.assertEqual(body["noticeResults"], [{"announcementId": 2}])

    def test_category_timeout_is_preserved(self):
        with patch.object(llm_client, "_post", return_value={}) as post:
            llm_client.rag_answer("질문", category="policy", conversation_history=[{"role": "user", "content": "q"}])
        self.assertEqual(post.call_args[1]["timeout"], llm_client.LLM_TIMEOUT_CHAT_POLICY)


class AsyncRagAnswerTest(unittest.IsolatedAsyncioTestCase):
    async def test_async_request_preserves_chat_payload(self):
        received = []

        def respond(request):
            received.append(request)
            return httpx.Response(200, json={"answer": "답변"})

        transport = httpx.MockTransport(respond)
        client_type = httpx.AsyncClient
        with patch.object(llm_client.httpx, "AsyncClient", side_effect=lambda **kwargs: client_type(
            transport=transport, **kwargs
        )):
            result = await llm_client.async_rag_answer(
                "질문", category="policy", user_context={"userId": 1}, notice_results=[]
            )

        self.assertEqual(result, {"answer": "답변"})
        self.assertEqual(received[0].url.path, "/rag/chat")
        self.assertEqual(received[0].method, "POST")
        self.assertEqual(json.loads(received[0].content), {
            "category": "policy", "question": "질문",
            "userContext": {"userId": 1}, "noticeResults": [],
        })


if __name__ == "__main__":
    unittest.main()
