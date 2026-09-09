"""校验手册 QA 的配比、字段及 PDF 原文证据，生成校验报告和可读题单。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {
    "error_code_troubleshooting": ("精确代码与排错", 35),
    "warranty_liability": ("免责与保修细则", 30),
    "multi_step_comparison": ("多步骤/参数比对", 20),
    "negative_refusal": ("越界负向拒答", 15),
}


def validate(examples: list[dict], pdf_root: Path) -> dict:
    errors = []
    counts = Counter()
    questions = set()
    case_ids = set()
    source_counts = Counter()
    evidence_count = 0
    boundary_count = 0
    cross_document_count = 0
    cross_page_count = 0

    @lru_cache(maxsize=None)
    def reader(relative_path: str) -> PdfReader:
        return PdfReader(pdf_root / relative_path)

    @lru_cache(maxsize=None)
    def page_text(relative_path: str, page_number: int) -> str:
        return reader(relative_path).pages[page_number].extract_text() or ""

    for index, example in enumerate(examples, 1):
        case_id = example["metadata"]["case_id"]
        outputs = example["outputs"]
        question = example["inputs"]["question"]
        category = outputs["category"]
        counts[category] += 1

        def check(condition: bool, message: str) -> None:
            if not condition:
                errors.append(f"{case_id}: {message}")

        check(case_id == f"manual-{index:03}", "题号应连续且与顺序一致")
        check(case_id not in case_ids, "题号重复")
        check(question not in questions and bool(question.strip()), "问题为空或重复")
        check(set(example["inputs"]) == {"question"}, "模型输入只能含问题，不能泄露参考答案")
        check(category in CATEGORIES, "未知类别")
        check(example["metadata"]["category"] == category, "元数据类别不一致")
        check(bool(outputs["ground_truth_answer"].strip()), "标准答案为空")
        check(outputs["reference_answer"] == outputs["ground_truth_answer"], "兼容答案字段不一致")
        check(bool(outputs["required_facts"]), "缺少评分事实")
        check(all(isinstance(f, str) and f.strip() for f in outputs["required_facts"]), "评分事实无效")
        case_ids.add(case_id)
        questions.add(question)

        gold = outputs["gold_sources"]
        boundary = outputs["boundary_sources"]
        should_answer = category != "negative_refusal"
        check(outputs["should_answer"] is should_answer, "回答/拒答标记与类别冲突")
        check(bool(gold) is should_answer, "可回答题必须有证据，负向题不可伪造支持证据")
        check(outputs["evidence_quote"] == [s["evidence_quote"] for s in gold], "证据别名不一致")
        if not should_answer:
            check(bool(boundary), "负向题缺少人工审查用的边界参考")
            check(bool(outputs["forbidden_claims"]), "负向题缺少禁止编造的断言")

        for source in gold + boundary:
            relative_path = source["source_path"]
            page_number = source["page_number"]
            quote = source["evidence_quote"]
            check(Path(relative_path).name == source["filename"], "文件名与相对路径不符")
            check(source["pdf_page"] == page_number + 1, "PDF 页与零基索引不一致")
            check(quote == source["must_contain"], "兼容证据字段不一致")
            check(bool(quote.strip()), "证据为空")
            try:
                document = reader(relative_path)
                check(0 <= page_number < len(document.pages), "页码超出 PDF 范围")
                if 0 <= page_number < len(document.pages):
                    check(quote in page_text(relative_path, page_number), "证据不是指定页面的逐字原文")
            except (OSError, ValueError) as exc:
                errors.append(f"{case_id}: 无法读取 {relative_path}: {exc}")

        evidence_count += len(gold)
        boundary_count += len(boundary)
        for filename in {s["filename"] for s in gold + boundary}:
            source_counts[filename] += 1
        cross_document_count += len({s["filename"] for s in gold}) > 1
        cross_page_count += len({(s["filename"], s["page_number"]) for s in gold}) > 1

    expected = {key: count for key, (_, count) in CATEGORIES.items()}
    if dict(counts) != expected:
        errors.append(f"类别配比错误：{dict(counts)}，预期 {expected}")
    if len(examples) != 100:
        errors.append(f"题目数应为 100，实际 {len(examples)}")
    corpus_files = {p.name for p in pdf_root.rglob("*.pdf")}
    unused = sorted(corpus_files - source_counts.keys())
    return {
        "valid": not errors,
        "example_count": len(examples),
        "category_counts": dict(counts),
        "answerable_count": sum(e["outputs"]["should_answer"] for e in examples),
        "gold_evidence_quotes_verified": evidence_count if not errors else None,
        "boundary_quotes_verified": boundary_count if not errors else None,
        "covered_pdf_count": len(source_counts),
        "corpus_pdf_count": len(corpus_files),
        "cross_document_examples": cross_document_count,
        "cross_page_examples": cross_page_count,
        "examples_per_source": dict(sorted(source_counts.items())),
        "unused_pdfs": unused,
        "page_convention": "page_number 为零基索引；pdf_page 为 PDF 阅读器一基页码",
        "verification": "原文逐字包含、配比、题号、问题去重和字段一致性；不是 RAG 运行得分或语义裁判结果",
        "errors": errors,
    }


def render_markdown(examples: list[dict]) -> str:
    lines = ["# 设备手册 RAG 评测集：100 题", "", "证据页码使用 PDF 阅读器从 1 开始的页码。JSON 的 page_number 则与项目保持零基索引。", ""]
    for example in examples:
        outputs = example["outputs"]
        lines.extend([
            f"## {example['metadata']['case_id']} | {CATEGORIES[outputs['category']][0]}",
            "", f"**问题**：{example['inputs']['question']}", "",
            f"**标准答案**：{outputs['ground_truth_answer']}", "",
            "**评分事实**：" + "；".join(outputs["required_facts"]), "",
        ])
        if outputs["forbidden_claims"]:
            lines.extend(["**禁止断言**：" + "；".join(outputs["forbidden_claims"]), ""])
        sources = outputs["gold_sources"]
        if not sources:
            lines.extend(["**负向样本**：无支持题述承诺或功能的标准证据。以下仅为边界参考，不计入检索召回分母。", ""])
            sources = outputs["boundary_sources"]
        for source in sources:
            lines.extend([f"来源：`{source['filename']}`，PDF 第 {source['pdf_page']} 页。", ""])
            lines.extend("> " + line for line in source["evidence_quote"].splitlines())
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "datasets/manual_qa_100.json")
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=ROOT / "reports/manual_qa_100_validation.json")
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    examples = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = validate(examples, args.pdf_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["valid"]:
        raise SystemExit(1)
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(examples), encoding="utf-8")


if __name__ == "__main__":
    main()
