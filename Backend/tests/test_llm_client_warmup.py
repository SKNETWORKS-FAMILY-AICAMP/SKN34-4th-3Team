"""기동 워밍업이 LLM 자체 warm-up을 기다리고, 끝내 준비되지 않을 때만 재색인하는지 검증한다."""

import itertools
import unittest
from unittest.mock import patch

from core import llm_client


NOT_READY = {"index_ready": False}
READY = {"index_ready": True, "chunk_count": 10}


class EnsureIndexReadyTest(unittest.TestCase):
    def setUp(self):
        patches = [
            patch.object(llm_client.time, "sleep"),
            patch.object(llm_client, "LLM_WARMUP_WAIT", 30),
            # 호출마다 10초씩 흐른 것으로 본다.
            patch.object(llm_client.time, "monotonic", side_effect=itertools.count(0, 10)),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_already_ready_skips_reindex(self):
        with patch.object(llm_client, "_get", return_value=READY), \
             patch.object(llm_client, "reindex") as reindex:
            self.assertTrue(llm_client.ensure_index_ready())
        reindex.assert_not_called()

    def test_waits_for_llm_warm_up_without_reindex(self):
        with patch.object(llm_client, "_get", side_effect=[NOT_READY, NOT_READY, READY]), \
             patch.object(llm_client, "reindex") as reindex:
            self.assertTrue(llm_client.ensure_index_ready())
        reindex.assert_not_called()

    def test_reindexes_once_after_wait_deadline(self):
        with patch.object(llm_client, "_get", return_value=NOT_READY), \
             patch.object(llm_client, "reindex", return_value={"status": "ready"}) as reindex:
            self.assertTrue(llm_client.ensure_index_ready())
        reindex.assert_called_once_with()

    def test_unreachable_llm_returns_false(self):
        with patch.object(llm_client, "_get", return_value=None), \
             patch.object(llm_client, "reindex") as reindex:
            self.assertFalse(llm_client.ensure_index_ready())
        reindex.assert_not_called()


if __name__ == "__main__":
    unittest.main()
