"""문서 API의 LLM 오류 상태와 사유가 보존되는지 검증한다."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from core import llm_client


class StrictPostTest(unittest.TestCase):
    def test_http_error_message_is_preserved(self):
        body = json.dumps({
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "입력 가능한 텍스트 필드가 없습니다.",
            }
        }).encode("utf-8")
        error = urllib.error.HTTPError("http://llm/test", 422, "error", {}, io.BytesIO(body))
        with patch.object(llm_client.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(llm_client.LLMRequestError) as raised:
                llm_client._post_strict("/test", {})
        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(raised.exception.message, "입력 가능한 텍스트 필드가 없습니다.")

    def test_wrapped_timeout_is_504(self):
        error = urllib.error.URLError(TimeoutError("timed out"))
        with patch.object(llm_client.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(llm_client.LLMRequestError) as raised:
                llm_client._post_strict("/test", {})
        self.assertEqual(raised.exception.status_code, 504)


if __name__ == "__main__":
    unittest.main()
