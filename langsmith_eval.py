from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Annotated, Any
from uuid import uuid4

from langchain_openai import ChatOpenAI
from langsmith import Client, evaluate
from pydantic import BaseModel, Field

# 项目根目录加入 sys.path，以便使用 backend 包导入
project_root = os.path.dirname(__file__)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.env import load_env

load_env()

DATASET_ID = "21478b5b-ff06-4cd8-b2da-9304a696837e"
DATASET_NAME = "中文生态环境与规划RAG评测集40题-文字版公报"
EXPERIMENT_PREFIX = "中文生态环境RAG-llm-judge-current"
DEFAULT_REUSE_EXPERIMENT_ID = "81cd70b7-9dbd-43eb-ae98-4831a4411676"

RAW_TOOL_TEXT_MARKERS = (
    "Retrieved Chunks:",
    "Web Search Sources:",
    "TOOL_CALL_LIMIT_REACHED",
)

UNANSWERABLE_MARKERS = (
    "未检索到",
    "没有检索到",
    "没有找到",
    "未找到相关",
    "知识库中未",
    "资料中未",
    "无法根据",
    "无法从",
    "依据不足",
    "缺乏依据",
    "不能确定",
    "无法回答",
    "无法确认",
    "未给出",
    "没有给出",
    "未列出",
    "没有列出",
    "未提及",
    "没有提及",
    "并未提供",
    "并未列出",
    "不包含",
    "无相关依据",
    "没有完整",
)

HIGH_RISK_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:\d+(?:\.\d+)?\s*(?:%|％|个百分点|微克|吨|万吨|亿吨|万亩|亿立方米|个|年|类)|20\d{2}年)"
)

JUDGE_MODEL = os.getenv("JUDGE_MODEL") or os.getenv("GRADE_MODEL") or os.getenv("FAST_MODEL") or os.getenv("MODEL")
JUDGE_MAX_EVIDENCE_CHARS = int(os.getenv("JUDGE_MAX_EVIDENCE_CHARS", "1200"))
_chat_with_agent = None
_judge = None
_raw_judge = None
_judge_cache: dict[str, "RagJudgeGrade"] = {}


class RagJudgeGrade(BaseModel):
    reasoning: Annotated[str, "简要说明主要扣分点或通过原因"]
    answer_accuracy: float = Field(ge=0, le=1, description="回答是否与参考答案和关键事实一致")
    faithfulness: float = Field(ge=0, le=1, description="回答中的事实是否能被检索证据支撑")
    completeness: float = Field(ge=0, le=1, description="回答是否覆盖 required_facts")
    citation_quality: float | None = Field(default=None, ge=0, le=1, description="引用是否存在且支撑对应事实")
    refusal_quality: float | None = Field(default=None, ge=0, le=1, description="不可回答样本是否正确拒答且不编造")
    cross_document_synthesis: float | None = Field(default=None, ge=0, le=1, description="跨文档题是否综合多个来源")
    trend_reasoning: float | None = Field(default=None, ge=0, le=1, description="趋势题是否覆盖年份数值并正确判断趋势")


def _get_chat_with_agent():
    global _chat_with_agent
    if _chat_with_agent is None:
        _chat_with_agent = importlib.import_module("backend.chat.service").chat_with_agent
    return _chat_with_agent


def _get_judge():
    global _judge
    if _judge is None:
        if not JUDGE_MODEL:
            raise RuntimeError("缺少 JUDGE_MODEL/GRADE_MODEL/FAST_MODEL/MODEL，无法运行 LLM-as-Judge。")
        base = ChatOpenAI(
            model=JUDGE_MODEL,
            api_key=os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            temperature=0,
            timeout=90,
            max_retries=2,
        )
        _judge = base.with_structured_output(RagJudgeGrade, method="json_schema", strict=True)
    return _judge


def _get_raw_judge():
    global _raw_judge
    if _raw_judge is None:
        if not JUDGE_MODEL:
            raise RuntimeError("缺少 JUDGE_MODEL/GRADE_MODEL/FAST_MODEL/MODEL，无法运行 LLM-as-Judge。")
        _raw_judge = ChatOpenAI(
            model=JUDGE_MODEL,
            api_key=os.getenv("ARK_API_KEY") or os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("BASE_URL"),
            temperature=0,
            timeout=90,
            max_retries=2,
        )
    return _raw_judge


def _extract_answer(outputs: Any) -> str:
    if isinstance(outputs, dict):
        answer = outputs.get("response") or outputs.get("answer") or outputs.get("output")
        return str(answer or "").strip()
    if hasattr(outputs, "outputs") and isinstance(outputs.outputs, dict):
        answer = (
            outputs.outputs.get("response")
            or outputs.outputs.get("answer")
            or outputs.outputs.get("output")
        )
        return str(answer or "").strip()
    return ""


def _get_outputs(value: Any) -> dict:
    if hasattr(value, "outputs") and isinstance(value.outputs, dict):
        return value.outputs or {}
    if isinstance(value, dict):
        outputs = value.get("outputs")
        if isinstance(outputs, dict):
            return outputs
        return value
    return {}


def _get_inputs(value: Any) -> dict:
    if hasattr(value, "inputs") and isinstance(value.inputs, dict):
        return value.inputs or {}
    if isinstance(value, dict):
        inputs = value.get("inputs")
        if isinstance(inputs, dict):
            return inputs
    return {}


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"\[(?:\d+|citation needed)\]", "", text)
    text = text.replace("pm 2.5", "pm2.5").replace("pm₂.₅", "pm2.5")
    return re.sub(r"[\s，。、“”‘’：:；;,.!?！？（）()\[\]【】《》<>\"'`~\-—_/\\]+", "", text)


def _normalize_filename(value: Any) -> str:
    filename = os.path.basename(str(value or "").strip())
    return unicodedata.normalize("NFKC", filename).lower()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _fact_text(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("fact", "text", "content", "answer", "value"):
            if value.get(key):
                return str(value[key])
        return " ".join(str(v) for v in value.values() if v is not None)
    return str(value or "")


def _parse_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"false", "0", "no", "n", "否", "不应回答"}:
        return False
    if normalized in {"true", "1", "yes", "y", "是", "应回答"}:
        return True
    return default


def _extract_rag_trace(outputs: dict) -> dict:
    rag_trace = outputs.get("rag_trace")
    return rag_trace if isinstance(rag_trace, dict) else {}


def _extract_retrieved_chunks(outputs: dict) -> list[dict]:
    chunks = outputs.get("retrieved_chunks")
    if not isinstance(chunks, list):
        chunks = _extract_rag_trace(outputs).get("retrieved_chunks")
    return [chunk for chunk in (chunks or []) if isinstance(chunk, dict)]


def _gold_filename(gold_source: Any) -> str:
    if isinstance(gold_source, dict):
        for key in ("filename", "file_name", "source", "document", "doc", "file"):
            if gold_source.get(key):
                return _normalize_filename(gold_source[key])
        return ""
    return _normalize_filename(gold_source)


def _gold_page(gold_source: Any) -> int | None:
    if not isinstance(gold_source, dict):
        return None
    for key in ("page_number", "page", "page_index"):
        if gold_source.get(key) is not None:
            try:
                return int(gold_source[key])
            except (TypeError, ValueError):
                return None
    return None


def _gold_must_contain(gold_source: Any) -> str:
    if not isinstance(gold_source, dict):
        return ""
    return str(gold_source.get("must_contain") or gold_source.get("evidence") or "").strip()


def _matches_gold_source(chunk: dict, gold_source: Any) -> bool:
    chunk_filename = _normalize_filename(
        chunk.get("filename") or chunk.get("source") or chunk.get("document")
    )
    if not chunk_filename:
        return False

    gold_filename = _gold_filename(gold_source)
    if gold_filename:
        return chunk_filename == gold_filename or chunk_filename in gold_filename or gold_filename in chunk_filename

    if isinstance(gold_source, str):
        normalized_gold = unicodedata.normalize("NFKC", gold_source).lower()
        return chunk_filename in normalized_gold

    return False


def _matches_gold_page(chunk: dict, gold_source: Any) -> bool:
    gold_page = _gold_page(gold_source)
    if gold_page is None:
        return _matches_gold_source(chunk, gold_source)
    try:
        chunk_page = int(chunk.get("page_number"))
    except (TypeError, ValueError):
        return False
    return _matches_gold_source(chunk, gold_source) and chunk_page == gold_page


def _matches_gold_evidence(chunk: dict, gold_source: Any) -> bool:
    must_contain = _gold_must_contain(gold_source)
    if not must_contain:
        return _matches_gold_page(chunk, gold_source)
    return _matches_gold_source(chunk, gold_source) and _normalize_text(must_contain) in _normalize_text(chunk.get("text"))


def _metric(score: float | int | bool | None, comment: str) -> dict:
    return {"score": int(score) if isinstance(score, bool) else score, "comment": comment}


def _clip_text(value: Any, limit: int = JUDGE_MAX_EVIDENCE_CHARS) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...[截断]"


def _evidence_for_judge(outputs: dict) -> list[dict[str, Any]]:
    evidence = []
    for index, chunk in enumerate(_extract_retrieved_chunks(outputs)[:5], start=1):
        evidence.append(
            {
                "index": index,
                "filename": chunk.get("filename") or chunk.get("source") or "",
                "page_number": chunk.get("page_number"),
                "rerank_score": chunk.get("rerank_score"),
                "text": _clip_text(chunk.get("text")),
            }
        )
    return evidence


def _judge_payload(run: Any, example: Any) -> dict[str, Any]:
    run_outputs = _get_outputs(run)
    example_outputs = _get_outputs(example)
    return {
        "question": _get_inputs(example).get("question") or _get_inputs(run).get("question"),
        "category": example_outputs.get("category"),
        "should_answer": _parse_bool(example_outputs.get("should_answer"), default=True),
        "reference_answer": example_outputs.get("reference_answer"),
        "required_facts": [_fact_text(fact) for fact in _as_list(example_outputs.get("required_facts"))],
        "gold_sources": example_outputs.get("gold_sources") or [],
        "actual_response": _extract_answer(run_outputs),
        "retrieved_evidence": _evidence_for_judge(run_outputs),
    }


def _empty_grade(reasoning: str) -> RagJudgeGrade:
    return RagJudgeGrade(
        reasoning=reasoning,
        answer_accuracy=0,
        faithfulness=0,
        completeness=0,
        citation_quality=0,
        refusal_quality=None,
        cross_document_synthesis=None,
        trend_reasoning=None,
    )


def _parse_json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError(f"模型未返回 JSON：{text[:200]}")
    return json.loads(match.group(0))


def _coerce_grade(value: Any) -> RagJudgeGrade:
    if isinstance(value, RagJudgeGrade):
        return value
    if isinstance(value, dict):
        return RagJudgeGrade.model_validate(value)
    if hasattr(value, "content"):
        return RagJudgeGrade.model_validate(_parse_json_object(str(value.content)))
    return RagJudgeGrade.model_validate(_parse_json_object(str(value)))


def _judge_grade(run: Any, example: Any) -> RagJudgeGrade:
    payload = _judge_payload(run, example)
    cache_key = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if cache_key in _judge_cache:
        return _judge_cache[cache_key]

    if not payload["actual_response"]:
        grade = _empty_grade("回答为空。")
        _judge_cache[cache_key] = grade
        return grade

    prompt = (
        "你是中文 RAG 系统的严格评估器。请只根据给定问题、参考答案、关键事实、gold_sources 和检索证据评分，"
        "不要引入外部知识。所有分数使用 0 到 1 的小数。\n\n"
        "评分口径：\n"
        "- answer_accuracy：最终回答是否回答了问题，且与 reference_answer/required_facts 一致。\n"
        "- faithfulness：回答中的事实、数字、年份、比较关系是否都能被 retrieved_evidence 支撑。\n"
        "- completeness：是否覆盖 required_facts；允许同义表达，不要求逐字一致。\n"
        "- citation_quality：可回答样本是否有 [1] 这类引用，且引用证据能支撑相应事实；不可回答样本可为 null。\n"
        "- refusal_quality：should_answer=false 时，是否明确说明资料未提供且没有编造；可回答样本为 null。\n"
        "- cross_document_synthesis：category=cross_document 时，是否正确综合多个 gold source；其他类别为 null。\n"
        "- trend_reasoning：category=trend 时，是否覆盖所有年份数值并判断趋势；其他类别为 null。\n\n"
        "如果回答包含证据中没有的关键数字、年份或确定性结论，应降低 faithfulness 和 answer_accuracy。"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]

    try:
        result = _get_judge().invoke(messages)
    except Exception:
        result = _get_raw_judge().invoke(
            [
                {
                    "role": "system",
                    "content": prompt
                    + "\n必须返回 JSON，对象字段为 reasoning, answer_accuracy, faithfulness, completeness, citation_quality, refusal_quality, cross_document_synthesis, trend_reasoning。",
                },
                messages[1],
            ],
            response_format={"type": "json_object"},
        )

    grade = _coerce_grade(result)
    _judge_cache[cache_key] = grade
    return grade


def retrieval_source_hit_at_5(run: Any, example: Any) -> dict:
    run_outputs = _get_outputs(run)
    reference_outputs = _get_outputs(example)
    chunks = _extract_retrieved_chunks(run_outputs)[:5]
    gold_sources = _as_list(reference_outputs.get("gold_sources"))
    should_answer = _parse_bool(reference_outputs.get("should_answer"), default=True)

    if not gold_sources:
        if not should_answer:
            return _metric(None, "不可回答样本未提供 gold_sources，不计入 source hit。")
        return _metric(0, "缺少 gold_sources，无法判断检索命中。")

    matched = [gold for gold in gold_sources if any(_matches_gold_source(chunk, gold) for chunk in chunks)]
    retrieved_files = [chunk.get("filename", "") for chunk in chunks]
    return _metric(len(matched) / len(gold_sources), f"source_hit={len(matched)}/{len(gold_sources)}; top5={retrieved_files}")


def retrieval_page_hit_at_5(run: Any, example: Any) -> dict:
    run_outputs = _get_outputs(run)
    reference_outputs = _get_outputs(example)
    chunks = _extract_retrieved_chunks(run_outputs)[:5]
    gold_sources = _as_list(reference_outputs.get("gold_sources"))
    gold_with_page = [gold for gold in gold_sources if _gold_page(gold) is not None]

    if not gold_with_page:
        return _metric(None, "gold_sources 未提供页码，不计入 page hit。")

    matched = [gold for gold in gold_with_page if any(_matches_gold_page(chunk, gold) for chunk in chunks)]
    return _metric(len(matched) / len(gold_with_page), f"page_hit={len(matched)}/{len(gold_with_page)}")


def retrieval_evidence_hit_at_5(run: Any, example: Any) -> dict:
    run_outputs = _get_outputs(run)
    reference_outputs = _get_outputs(example)
    chunks = _extract_retrieved_chunks(run_outputs)[:5]
    gold_sources = _as_list(reference_outputs.get("gold_sources"))
    gold_with_evidence = [gold for gold in gold_sources if _gold_must_contain(gold)]

    if not gold_with_evidence:
        return _metric(None, "gold_sources 未提供 must_contain，不计入 evidence hit。")

    matched = [gold for gold in gold_with_evidence if any(_matches_gold_evidence(chunk, gold) for chunk in chunks)]
    return _metric(len(matched) / len(gold_with_evidence), f"evidence_hit={len(matched)}/{len(gold_with_evidence)}")


def answer_fact_coverage(run: Any, example: Any) -> dict:
    run_outputs = _get_outputs(run)
    reference_outputs = _get_outputs(example)
    answer = _normalize_text(_extract_answer(run_outputs))
    required_facts = [_fact_text(fact) for fact in _as_list(reference_outputs.get("required_facts"))]
    required_facts = [fact for fact in required_facts if fact.strip()]

    if not required_facts:
        return _metric(None, "无 required_facts，不计入事实覆盖。")
    if not answer:
        return _metric(0, "回答为空。")

    missing = [fact for fact in required_facts if _normalize_text(fact) not in answer]
    covered = len(required_facts) - len(missing)
    return _metric(covered / len(required_facts), f"fact_coverage={covered}/{len(required_facts)}; missing={missing[:3]}")


def citation_present(run: Any, example: Any) -> dict:
    reference_outputs = _get_outputs(example)
    should_answer = _parse_bool(reference_outputs.get("should_answer"), default=True)
    if not should_answer:
        return _metric(None, "不可回答样本不要求引用。")
    answer = _extract_answer(_get_outputs(run))
    citations = re.findall(r"\[\d+\]", answer)
    return _metric(bool(citations), f"citations={citations[:8]}")


def unanswerable_accuracy(run: Any, example: Any) -> dict:
    reference_outputs = _get_outputs(example)
    should_answer = _parse_bool(reference_outputs.get("should_answer"), default=True)
    if should_answer:
        return _metric(None, "可回答样本不计入拒答准确率。")

    answer = _extract_answer(_get_outputs(run))
    if not answer:
        return _metric(0, "不可回答样本的回答为空，未明确说明依据不足。")

    matched = [marker for marker in UNANSWERABLE_MARKERS if marker in answer]
    return _metric(bool(matched), f"unanswerable_markers={matched[:5]}")


def unanswerable_no_fabrication(run: Any, example: Any) -> dict:
    reference_outputs = _get_outputs(example)
    should_answer = _parse_bool(reference_outputs.get("should_answer"), default=True)
    if should_answer:
        return _metric(None, "可回答样本不计入拒答编造检查。")

    answer = _extract_answer(_get_outputs(run))
    risky_numbers = HIGH_RISK_NUMBER_RE.findall(answer)
    return _metric(not risky_numbers, f"risky_numbers={risky_numbers[:8]}")


def no_tool_raw_leak(run: Any, example: Any) -> dict:
    answer = _extract_answer(_get_outputs(run))
    leaked = [marker for marker in RAW_TOOL_TEXT_MARKERS if marker in answer]
    return _metric(not leaked, f"raw_tool_text_leak={leaked}")


def llm_answer_accuracy(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.answer_accuracy, grade.reasoning)


def llm_faithfulness(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.faithfulness, grade.reasoning)


def llm_completeness(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.completeness, grade.reasoning)


def llm_citation_quality(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.citation_quality, grade.reasoning)


def llm_refusal_quality(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.refusal_quality, grade.reasoning)


def llm_cross_document_synthesis(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.cross_document_synthesis, grade.reasoning)


def llm_trend_reasoning(run: Any, example: Any) -> dict:
    grade = _judge_grade(run, example)
    return _metric(grade.trend_reasoning, grade.reasoning)


RULE_EVALUATORS = [
    retrieval_source_hit_at_5,
    retrieval_page_hit_at_5,
    retrieval_evidence_hit_at_5,
    answer_fact_coverage,
    citation_present,
    unanswerable_accuracy,
    unanswerable_no_fabrication,
    no_tool_raw_leak,
]

LLM_EVALUATORS = [
    llm_answer_accuracy,
    llm_faithfulness,
    llm_completeness,
    llm_citation_quality,
    llm_refusal_quality,
    llm_cross_document_synthesis,
    llm_trend_reasoning,
]


# 直接调用现有完整 Agent 流程作为评估对象
def target_function(inputs: dict) -> dict:
    question = inputs["question"]
    session_id = f"langsmith_eval_{uuid4().hex}"
    result = _get_chat_with_agent()(
        user_text=question,
        user_id="langsmith_eval_user",
        session_id=session_id,
    )

    response_text = ""
    rag_trace = {}
    if isinstance(result, dict):
        response_text = str(result.get("response", "") or "")
        rag_trace = result.get("rag_trace", {}) or {}
    else:
        response_text = str(result)

    if not isinstance(rag_trace, dict):
        rag_trace = {}
    retrieved_chunks = rag_trace.get("retrieved_chunks") or []

    return {
        "response": response_text,
        "rag_trace": rag_trace,
        "retrieved_chunks": retrieved_chunks,
        "tool_used": bool(rag_trace.get("tool_used") or retrieved_chunks),
        "tool_name": rag_trace.get("tool_name") or "",
        "retrieval_stage": rag_trace.get("retrieval_stage") or "",
    }


def _dataset_ref(args: argparse.Namespace) -> str:
    return args.dataset_id or args.dataset_name or DATASET_NAME


def _metric_names(evaluators: list) -> list[str]:
    return [evaluator.__name__ for evaluator in evaluators]


def _score_to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize_scores(rows: list[dict[str, Any]], metric_names: list[str]) -> dict[str, Any]:
    summary = {}
    for name in metric_names:
        values = [_score_to_float(row["metrics"].get(name, {}).get("score")) for row in rows]
        values = [value for value in values if value is not None]
        if not values:
            summary[name] = {"n": 0, "avg": None, "pass_rate": None}
            continue
        summary[name] = {
            "n": len(values),
            "avg": mean(values),
            "pass_rate": sum(1 for value in values if value >= 0.999) / len(values),
            "min": min(values),
            "max": max(values),
        }
    return summary


def _run_perf(rows: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [row["latency"] for row in rows if row.get("latency") is not None]
    tokens = [row["total_tokens"] for row in rows if row.get("total_tokens") is not None]
    return {
        "latency_avg": mean(latencies) if latencies else None,
        "latency_median": median(latencies) if latencies else None,
        "latency_max": max(latencies) if latencies else None,
        "tokens_avg": mean(tokens) if tokens else None,
        "tokens_median": median(tokens) if tokens else None,
        "tokens_max": max(tokens) if tokens else None,
    }


def _format_score(value: Any) -> str:
    number = _score_to_float(value)
    if number is None:
        return "N/A"
    return f"{number:.3f}"


def _report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = Path("reports")
    md_path = Path(args.report_md) if args.report_md else report_dir / f"langsmith_eval_{timestamp}.md"
    json_path = Path(args.report_json) if args.report_json else report_dir / f"langsmith_eval_{timestamp}.json"
    return md_path, json_path


def _write_report(payload: dict[str, Any], md_path: Path, json_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    overall = payload["overall"]
    perf = payload["performance"]
    lines = [
        f"# LangSmith RAG 评估报告",
        "",
        f"- Dataset: {payload['dataset'].get('name')} (`{payload['dataset'].get('id')}`)",
        f"- Experiment: {payload['experiment'].get('name')} (`{payload['experiment'].get('id')}`)",
        f"- Runs: {payload['run_count']}",
        f"- Error rate: {payload['experiment'].get('error_rate')}",
        f"- P50 latency: {payload['experiment'].get('latency_p50')}",
        f"- P99 latency: {payload['experiment'].get('latency_p99')}",
        f"- Avg latency: {_format_score(perf.get('latency_avg'))}s",
        f"- Avg tokens: {_format_score(perf.get('tokens_avg'))}",
        "",
        "## Overall Metrics",
        "",
        "| Metric | N | Avg | Pass Rate | Min | Max |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, stats in overall.items():
        pass_rate = stats.get("pass_rate")
        pass_rate_text = "N/A" if pass_rate is None else f"{pass_rate:.1%}"
        lines.append(
            f"| {name} | {stats.get('n', 0)} | {_format_score(stats.get('avg'))} | {pass_rate_text} | {_format_score(stats.get('min'))} | {_format_score(stats.get('max'))} |"
        )

    lines.extend(["", "## By Category", ""])
    for category, summary in payload["by_category"].items():
        lines.extend([f"### {category}", "", "| Metric | N | Avg | Pass Rate |", "| --- | ---: | ---: | ---: |"])
        for name, stats in summary.items():
            pass_rate = stats.get("pass_rate")
            pass_rate_text = "N/A" if pass_rate is None else f"{pass_rate:.1%}"
            lines.append(f"| {name} | {stats.get('n', 0)} | {_format_score(stats.get('avg'))} | {pass_rate_text} |")
        lines.append("")

    lines.extend(["## Low Score Samples", ""])
    for row in payload["low_score_samples"][:20]:
        failed = ", ".join(
            f"{name}={_format_score(metric.get('score'))}"
            for name, metric in row["metrics"].items()
            if _score_to_float(metric.get("score")) is not None and _score_to_float(metric.get("score")) < 0.8
        )
        lines.extend(
            [
                f"- `{row['run_id']}` / {row['category']} / {failed}",
                f"  - Q: {row['question']}",
                f"  - A: {_clip_text(row['answer'], 220)}",
            ]
        )

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _evaluate_existing_experiment(args: argparse.Namespace, evaluators: list) -> dict[str, Any]:
    client = Client()
    dataset = client.read_dataset(dataset_id=args.dataset_id) if args.dataset_id else client.read_dataset(dataset_name=args.dataset_name)
    project = client.read_project(project_id=args.reuse_experiment_id, include_stats=True)
    runs = list(client.list_runs(project_id=args.reuse_experiment_id, is_root=True, limit=args.limit))
    examples = {
        str(example.id): example
        for example in client.list_examples(dataset_id=str(dataset.id), limit=max(args.limit or 100, 100))
    }

    rows = []
    for index, run in enumerate(runs, start=1):
        example_id = str(getattr(run, "reference_example_id", "") or "")
        example = examples.get(example_id)
        if example is None:
            continue
        metrics = {}
        print(f"[{index}/{len(runs)}] evaluating run={run.id} example={example_id}")
        for evaluator in evaluators:
            try:
                metrics[evaluator.__name__] = evaluator(run, example)
            except Exception as exc:
                metrics[evaluator.__name__] = _metric(0, f"evaluator_error={type(exc).__name__}: {exc}")

        outputs = _get_outputs(run)
        trace = _extract_rag_trace(outputs)
        chunks = _extract_retrieved_chunks(outputs)
        rerank_scores = [
            float(chunk["rerank_score"])
            for chunk in chunks
            if isinstance(chunk, dict) and chunk.get("rerank_score") is not None
        ]
        rows.append(
            {
                "run_id": str(run.id),
                "example_id": example_id,
                "category": (_get_outputs(example).get("category") or "unknown"),
                "question": _get_inputs(example).get("question") or _get_inputs(run).get("question"),
                "answer": _extract_answer(outputs),
                "metrics": metrics,
                "latency": getattr(run, "latency", None),
                "total_tokens": getattr(run, "total_tokens", None),
                "retrieval_stage": outputs.get("retrieval_stage") or trace.get("retrieval_stage"),
                "retrieved_count": len(chunks),
                "rerank_score_top1": rerank_scores[0] if rerank_scores else None,
                "rerank_score_avg": mean(rerank_scores) if rerank_scores else None,
                "auto_merge_applied": trace.get("auto_merge_applied"),
            }
        )

    metric_names = _metric_names(evaluators)
    by_category = {}
    for category in sorted({row["category"] for row in rows}):
        by_category[category] = _summarize_scores(
            [row for row in rows if row["category"] == category],
            metric_names,
        )

    low_score_rows = sorted(
        rows,
        key=lambda row: min(
            [
                _score_to_float(metric.get("score"))
                for metric in row["metrics"].values()
                if _score_to_float(metric.get("score")) is not None
            ]
            or [1]
        ),
    )

    payload = {
        "dataset": {"id": str(dataset.id), "name": dataset.name, "description": dataset.description},
        "experiment": {
            "id": str(project.id),
            "name": project.name,
            "run_count": getattr(project, "run_count", None),
            "total_tokens": getattr(project, "total_tokens", None),
            "latency_p50": str(getattr(project, "latency_p50", None)),
            "latency_p99": str(getattr(project, "latency_p99", None)),
            "error_rate": getattr(project, "error_rate", None),
            "metadata": getattr(project, "metadata", None),
        },
        "run_count": len(rows),
        "overall": _summarize_scores(rows, metric_names),
        "by_category": by_category,
        "performance": _run_perf(rows),
        "retrieval_stage_counts": dict(Counter(row.get("retrieval_stage") for row in rows)),
        "auto_merge_counts": dict(Counter(str(row.get("auto_merge_applied")) for row in rows)),
        "rows": rows,
        "low_score_samples": low_score_rows,
    }
    md_path, json_path = _report_paths(args)
    _write_report(payload, md_path, json_path)
    print(f"报告已生成：{md_path}")
    print(f"原始 JSON：{json_path}")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行或复算 SuperMew LangSmith RAG 评估。")
    parser.add_argument("--dataset-id", default=DATASET_ID, help="LangSmith dataset id。")
    parser.add_argument("--dataset-name", default=DATASET_NAME, help="LangSmith dataset name。")
    parser.add_argument("--experiment-prefix", default=EXPERIMENT_PREFIX, help="新实验名前缀。")
    parser.add_argument("--reuse-experiment-id", default=None, help="只读取并复算已有 experiment/project id，不重新跑 Agent。")
    parser.add_argument("--limit", type=int, default=None, help="限制样本数量。")
    parser.add_argument("--judge-model", default=JUDGE_MODEL, help="LLM-as-Judge 模型名。")
    parser.add_argument("--no-llm", action="store_true", help="只运行规则指标，不调用 LLM judge。")
    parser.add_argument("--report-md", default=None, help="Markdown 报告输出路径。")
    parser.add_argument("--report-json", default=None, help="JSON 报告输出路径。")
    parser.add_argument(
        "--default-reuse",
        action="store_true",
        help=f"复算默认 experiment：{DEFAULT_REUSE_EXPERIMENT_ID}。",
    )
    return parser


def main() -> None:
    global JUDGE_MODEL
    args = _build_parser().parse_args()
    JUDGE_MODEL = args.judge_model
    evaluators = RULE_EVALUATORS if args.no_llm else RULE_EVALUATORS + LLM_EVALUATORS

    if args.default_reuse and not args.reuse_experiment_id:
        args.reuse_experiment_id = DEFAULT_REUSE_EXPERIMENT_ID

    if args.reuse_experiment_id:
        _evaluate_existing_experiment(args, evaluators)
        return

    data = args.dataset_id or args.dataset_name
    evaluate(
        target_function,
        data=data,
        evaluators=evaluators,
        experiment_prefix=args.experiment_prefix,
        max_concurrency=1,
        num_repetitions=1,
    )


if __name__ == "__main__":
    main()
