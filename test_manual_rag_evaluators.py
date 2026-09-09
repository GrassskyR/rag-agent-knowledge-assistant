import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import langsmith_eval
from manual_rag_evaluators import (
    CorrectnessGrade,
    FaithfulnessGrade,
    ManualRagEvaluators,
    RetrievalGrade,
    average_precision,
)


def example(should_answer=True):
    return {"inputs": {"question": "设备故障怎么处理？"}, "outputs": {
        "should_answer": should_answer, "ground_truth_answer": "检查参数后重试",
        "required_facts": ["检查参数", "重试"], "forbidden_claims": ["免费换整机"],
        "gold_sources": [{"filename": "manual.pdf", "evidence_quote": "检查参数后重试"}] if should_answer else [],
        "boundary_sources": [],
    }}


def run(chunks=2, answer="检查参数后重试"):
    return {"outputs": {"response": answer, "retrieved_chunks": [
        {"filename": "manual.pdf", "text": f"第{i}块", "page_number": i}
        for i in range(chunks)
    ]}}


class ManualEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.model = Mock()
        self.evaluators = ManualRagEvaluators(lambda: self.model)

    def set_grade(self, grade):
        self.model.with_structured_output.return_value.invoke.return_value = grade

    def test_average_precision_penalizes_late_relevant_chunks(self):
        self.assertEqual(average_precision([True, True, False]), 1)
        self.assertAlmostEqual(average_precision([False, True, True]), (1 / 2 + 2 / 3) / 2)
        self.assertEqual(average_precision([False, False]), 0)
        self.assertEqual(average_precision([]), 0)

    def test_retrieval_uses_indices_and_reuses_judgment(self):
        self.set_grade(RetrievalGrade.model_validate({
            "evidence": [{"evidence_index": 1, "covered": True, "chunk_indices": [2], "reason": "覆盖"}],
            "chunks": [{"chunk_index": 2, "relevant": True, "reason": "相关"},
                       {"chunk_index": 1, "relevant": False, "reason": "不相关"}],
        }))
        self.assertEqual(self.evaluators.context_recall(run(), example())["score"], 1)
        self.assertEqual(self.evaluators.context_precision(run(), example())["score"], 0.5)
        self.assertEqual(self.evaluators.retrieval_mrr_at_k(run(), example())["score"], 0.5)
        self.assertEqual(self.evaluators.retrieval_hit_at_k(run(), example())["score"], 1)
        self.assertEqual(self.model.with_structured_output.return_value.invoke.call_count, 1)

    def test_negative_retrieval_is_na_but_empty_positive_retrieval_is_zero(self):
        for evaluator in (self.evaluators.context_recall, self.evaluators.context_precision):
            self.assertIsNone(evaluator(run(), example(False))["score"])
            self.assertEqual(evaluator(run(0), example())["score"], 0)
        self.model.with_structured_output.assert_not_called()

    def test_missing_chunk_labels_are_errors_not_quality_scores(self):
        self.set_grade(RetrievalGrade.model_validate({
            "evidence": [{"evidence_index": 1, "covered": False, "chunk_indices": [], "reason": "未命中"}],
            "chunks": [{"chunk_index": 1, "relevant": False, "reason": "无关"}],
        }))
        with self.assertRaisesRegex(ValueError, "编号缺失"):
            self.evaluators.context_precision(run(), example())

    def test_context_is_complete_and_faithfulness_has_no_reference_answer(self):
        self.set_grade(FaithfulnessGrade.model_validate({
            "claims": [{"claim": "检查参数", "supported": True, "chunk_indices": [6], "reason": "原文"},
                       {"claim": "免费换机", "supported": False, "chunk_indices": [], "reason": "无依据"}],
            "refusal_only": False, "reason": "部分无依据",
        }))
        actual = run(6)
        actual["outputs"]["retrieved_chunks"][5]["text"] = "甲" * 2000 + "关键证据"
        self.assertEqual(self.evaluators.faithfulness(actual, example())["score"], 0.5)
        messages = self.model.with_structured_output.return_value.invoke.call_args.args[0]
        payload = json.loads(messages[1]["content"])
        self.assertEqual(set(payload), {"question", "actual_response", "retrieved_context"})
        self.assertEqual(len(payload["retrieved_context"]), 6)
        self.assertTrue(payload["retrieved_context"][5]["text"].endswith("关键证据"))

    def test_pure_refusal_is_faithful_without_factual_claims(self):
        self.set_grade(FaithfulnessGrade(claims=[], refusal_only=True, reason="仅说明资料不足"))
        self.assertEqual(self.evaluators.faithfulness(run(0, "资料不足，无法确认"), example(False))["score"], 1)

    def test_correctness_combines_facts_and_semantics(self):
        self.set_grade(CorrectnessGrade.model_validate({
            "facts": [{"fact_index": 1, "correct": True, "reason": "包含"},
                      {"fact_index": 2, "correct": False, "reason": "遗漏"}],
            "incorrect_claims": ["错误额外断言"], "forbidden_claim_violations": [],
            "semantic_similarity": 0.6, "refusal_appropriate": None, "reason": "部分正确",
        }))
        self.assertAlmostEqual(self.evaluators.answer_correctness(run(), example())["score"], 0.75 * 0.5 + 0.25 * 0.6)

    def test_forbidden_promise_overrides_high_similarity(self):
        self.set_grade(CorrectnessGrade.model_validate({
            "facts": [{"fact_index": i, "correct": True, "reason": "包含"} for i in (1, 2)],
            "incorrect_claims": ["免费换整机"], "forbidden_claim_violations": ["免费换整机"],
            "semantic_similarity": 1, "refusal_appropriate": True, "reason": "拒答后仍虚假承诺",
        }))
        self.assertEqual(self.evaluators.answer_correctness(run(), example(False))["score"], 0)
        self.assertEqual(self.evaluators.refusal_accuracy(run(), example(False))["score"], 0)
        payload = json.loads(self.model.with_structured_output.return_value.invoke.call_args.args[0][1]["content"])
        self.assertEqual(payload["forbidden_claims"], ["免费换整机"])

    def test_judge_error_is_cached_and_not_silently_scored_zero(self):
        self.model.with_structured_output.return_value.invoke.side_effect = TimeoutError("judge unavailable")
        for evaluator in (self.evaluators.context_recall, self.evaluators.context_precision):
            with self.assertRaises(TimeoutError):
                evaluator(run(), example())
        self.assertEqual(self.model.with_structured_output.return_value.invoke.call_count, 1)

    def test_refusal_with_unsupported_assertion_fails_even_if_judge_accepts_refusal(self):
        self.set_grade(CorrectnessGrade.model_validate({
            "facts": [{"fact_index": i, "correct": True, "reason": "包含"} for i in (1, 2)],
            "incorrect_claims": ["没有说明就断言不支持"], "forbidden_claim_violations": [],
            "semantic_similarity": 0.9, "refusal_appropriate": True, "reason": "拒答但无依据断言",
        }))
        self.assertEqual(self.evaluators.answer_correctness(run(), example(False))["score"], 0)
        self.assertEqual(self.evaluators.refusal_accuracy(run(), example(False))["score"], 0)

    def test_target_errors_are_not_counted_as_refusal_or_retrieval_misses(self):
        actual = SimpleNamespace(outputs={}, error="model timeout")
        for evaluator in (self.evaluators.context_recall, self.evaluators.faithfulness,
                          self.evaluators.answer_correctness, self.evaluators.refusal_accuracy):
            with self.assertRaisesRegex(RuntimeError, "被测运行失败"):
                evaluator(actual, example(False))

    def test_judge_credentials_and_endpoint_are_independent(self):
        with patch.dict("os.environ", {"JUDGE_API_KEY": "judge-key", "ARK_API_KEY": "target-key",
                                      "JUDGE_BASE_URL": "https://judge.invalid/v1", "BASE_URL": "https://target.invalid/v1"}), \
                patch.object(langsmith_eval, "_raw_judge", None), \
                patch.object(langsmith_eval, "ChatOpenAI") as constructor:
            langsmith_eval._get_raw_judge()
            self.assertEqual(constructor.call_args.kwargs["api_key"], "judge-key")
            self.assertEqual(constructor.call_args.kwargs["base_url"], "https://judge.invalid/v1")

    def test_judge_disables_thinking_by_default(self):
        with patch.dict("os.environ", {"JUDGE_EXTRA_BODY": ""}, clear=False), \
                patch.object(langsmith_eval, "_raw_judge", None), \
                patch.object(langsmith_eval, "ChatOpenAI") as constructor:
            langsmith_eval._get_raw_judge()
            self.assertEqual(constructor.call_args.kwargs["extra_body"], {"thinking": {"type": "disabled"}})

    def test_dataset_name_is_not_overridden_by_old_default_id(self):
        args = langsmith_eval._build_parser().parse_args(["--dataset-name", "manual-100"])
        self.assertEqual(langsmith_eval._dataset_ref(args), "manual-100")


if __name__ == "__main__":
    unittest.main()
