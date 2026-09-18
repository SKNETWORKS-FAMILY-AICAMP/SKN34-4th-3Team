"""로드맵 채팅 요청 계약 검증."""

import unittest

from pydantic import ValidationError

from schemas.chat import ChatMessageRequest


class ChatMessageRequestTest(unittest.TestCase):
    def test_roadmap_step_is_accepted_for_roadmap(self):
        request = ChatMessageRequest(
            category="roadmap",
            question="다음 할 일은?",
            roadmapStep="Z",
        )
        self.assertEqual(request.roadmapStep, "Z")

    def test_invalid_roadmap_step_is_rejected(self):
        with self.assertRaises(ValidationError):
            ChatMessageRequest(
                category="roadmap",
                question="다음 할 일은?",
                roadmapStep="G",
            )

    def test_roadmap_step_is_rejected_for_other_category(self):
        with self.assertRaises(ValidationError):
            ChatMessageRequest(
                category="tax",
                question="부가세 신고일은?",
                roadmapStep="F",
            )


if __name__ == "__main__":
    unittest.main()
