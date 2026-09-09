import unittest
from unittest.mock import patch

from backend.rag import utils


class MergeRerankTests(unittest.TestCase):
    def test_empty_merge_does_not_call_reranker(self):
        with patch.object(utils, "_rerank_documents") as rerank:
            docs, meta = utils.rerank_merged_documents("原始问题", [])
        self.assertEqual(docs, [])
        self.assertEqual(meta["merge_rerank_candidate_count"], 0)
        rerank.assert_not_called()

    def test_merged_candidates_are_reranked_with_full_query_and_ranked(self):
        docs = [
            {"chunk_id": "a", "text": "无关", "score": 0.9},
            {"chunk_id": "b", "text": "关键证据", "score": 0.8},
        ]
        with patch.object(utils, "_rerank_documents", return_value=(
            [{**docs[1], "rerank_score": 0.99}, {**docs[0], "rerank_score": 0.01}],
            {"rerank_applied": True, "rerank_error": None},
        )) as rerank:
            result, meta = utils.rerank_merged_documents("完整原始问题", docs)

        rerank.assert_called_once_with(query="完整原始问题", docs=docs, top_k=2)
        self.assertEqual([item["chunk_id"] for item in result], ["b", "a"])
        self.assertEqual([item["rrf_rank"] for item in result], [1, 2])
        self.assertTrue(meta["merge_rerank_applied"])

    def test_candidates_omitted_by_reranker_are_preserved_after_ranked_results(self):
        docs = [
            {"chunk_id": "a", "text": "a"},
            {"chunk_id": "b", "text": "b"},
            {"chunk_id": "c", "text": "c"},
        ]
        with patch.object(utils, "_rerank_documents", return_value=(
            [{**docs[1], "rerank_score": 0.9}],
            {"rerank_applied": True, "rerank_error": None},
        )):
            result, meta = utils.rerank_merged_documents("问题", docs)

        self.assertEqual([item["chunk_id"] for item in result], ["b", "a", "c"])
        self.assertEqual(meta["merge_rerank_preserved_count"], 2)
        self.assertEqual([item["rrf_rank"] for item in result], [1, 2, 3])

    def test_rerank_error_keeps_all_candidates_and_reports_error(self):
        docs = [{"chunk_id": "a", "text": "a"}, {"chunk_id": "b", "text": "b"}]
        with patch.object(utils, "_rerank_documents", return_value=(
            docs, {"rerank_applied": True, "rerank_error": "HTTP 500"},
        )):
            result, meta = utils.rerank_merged_documents("问题", docs)
        self.assertEqual(len(result), 2)
        self.assertEqual(meta["merge_rerank_error"], "HTTP 500")


if __name__ == "__main__":
    unittest.main()
