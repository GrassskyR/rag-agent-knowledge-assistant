# 设备手册 RAG 评测集

`manual_qa_100.json` 是 LangSmith examples 数组，`manual_qa_100.md` 是含原文证据的可读题单。
资料仅取自 `/home/missi/project/web/fetch/manual/download` 下的 20 份 PDF，不使用模型常识补写资料外的功能、故障解释或保修承诺。

| 类别 | outputs.category | 数量 |
| --- | --- | ---: |
| 精确代码与排错 | error_code_troubleshooting | 35 |
| 免责与保修细则 | warranty_liability | 30 |
| 多步骤/参数比对 | multi_step_comparison | 20 |
| 越界负向拒答 | negative_refusal | 15 |

第二类基于实际可用的有限保修、耗材、维修及免责条款；这些 PDF 没有提供完整的中国“三包”细则，不能补造七天/十五天退换承诺。问题涉及的保修期限、政策和产品功能均以所给历史版本手册为准，不作为现行政策核验。

## 字段

模型输入只有 `inputs.question`，其余均为评测参考，不能拼入被测模型的提示词。

| 字段 | 含义 |
| --- | --- |
| outputs.ground_truth_answer | 标准答案，保留条件、处理顺序和适用机型 |
| outputs.reference_answer | 与标准答案相同，兼容已有 `langsmith_eval.py` |
| outputs.required_facts | 需要覆盖的事实，允许同义表达 |
| outputs.forbidden_claims | 不得作出的错误承诺或虚构事实 |
| outputs.evidence_quote | 标准证据原文字符串数组，与 gold_sources 一一对应 |
| outputs.gold_sources | 文件名、相对路径、页码和逐字证据；must_contain 与 evidence_quote 相同 |
| outputs.should_answer | 85 条为 true，15 条负向题为 false |
| outputs.boundary_sources | 负向题附近的相关说明，用于人工审查；不属于支持题述功能或承诺的标准证据 |
| metadata.case_id / category / product | 稳定题号、分类和具体产品，便于 LangSmith 筛选 |

`gold_sources[].page_number` 沿用 `backend/indexing/document_loader.py` 的 **零基 PDF 页索引**，`pdf_page` 是阅读器中从 1 开始的物理页码，不是书内印刷页码。证据保留 PDF 提取后的原文及换行，繁体原文不转换成简体。校验使用与项目 PDF 加载器同源的 `pypdf` 文本提取。

## 指标口径

以下口径由 `langsmith_eval.py --metrics manual` 和 `manual_rag_evaluators.py` 实现：

| 指标 | 计算方式 | 裁判输入 |
| --- | --- | --- |
| context_recall | 裁判判断每条标准证据的必要事实是否被覆盖；已覆盖证据数 / 全部标准证据数。允许同义、跨块及同一手册重复条款，不能仅命中文件名或相邻代码。 | 问题、标准答案/证据、全部实际检索块，不含生成答案。 |
| context_precision | 按实际返回顺序逐块判相关性，计算 AP@K：sum(P@i × relevant_i) / 前 K 块中的相关块数，无相关块时为 0。默认 K=5。 | 与 recall 共享一次检索判断；不重排实际块，不以 rerank 分值代替相关性。 |
| faithfulness | 被上下文支持的原子事实数 / 回答中的原子事实数；纯粹说明资料不足的拒答为 1，空回答为 0。 | 独立请求，只给问题、实际回答和完整实际上下文，不传标准答案和标准证据。 |
| answer_correctness | 0.75 × 事实 F1 + 0.25 × 裁判语义一致度。TP 为正确覆盖的 required_facts，FN 为遗漏/错误事实，FP 为不重复的额外错误主张；F1=2TP/(2TP+FN+FP)。违反 forbidden_claims，或负向题拒答不合格/附加错误断言时记 0。 | 独立请求，比较实际回答与标准答案、事实、标准/边界证据和禁止断言；实际上下文仅可验证不与标准冲突的额外事实。语义一致度由 LLM 判断，不是 embedding 余弦值。 |

负向题没有正向 gold evidence，`context_recall` 和基于标准相关块的 `context_precision` 应记为 N/A，不计入均值分母；继续评估忠实度、回答准确性和拒答质量。允许纠正错误前提及提供资料内的有限事实。不能因出现“无法确认”等词就判通过：拒答后继续承诺免费、编造步骤、版本或价格仍应失败。

同时输出 `retrieval_hit_at_k`、`retrieval_mrr_at_k` 和仅对负向题计分的 `refusal_accuracy`。比较 Rerank 版本时固定候选集、K、数据集和裁判口径。报告列出类别均分、每项计分题数、被测执行错误数和裁判错误数；API 超时或返回编号无效记为评测错误，不冒充 0 分或正常 N/A。

`--metrics legacy` 保留旧生态环境评测指标；它的数字正则、字面事实命中及截断上下文口径不适用于替代本次四项指标。

## 复核

```bash
uv run --no-sync python scripts/validate_manual_dataset.py \
  --pdf-root /home/missi/project/web/fetch/manual/download \
  --markdown datasets/manual_qa_100.md
```

报告写入 `reports/manual_qa_100_validation.json`，验证 100 条总数、配比、问题唯一性、字段一致性，以及每段证据在指定 PDF 页中的逐字存在性。这个报告是数据校验，**不是系统四项指标的实际分数**。负向题边界段落可校验，但不能用“段落存在”自动证明全库不存在其他答案。

## 导入与评测

已上传数据集：`设备手册RAG评测集100题-v1`（ID `527bc11f-6d49-41ba-ad24-d66228744d46`）。100 条输入、输出均已与本地核对，题号元数据也已补齐。

首次导入其他版本时，可使用 CLI；当前安装版本的 CLI 不保留本地 metadata，需要使用 SDK 补写 case_id/category/product，或直接通过 SDK 的 `create_examples(examples=..., dataset_id=...)` 导入完整 examples。

```bash
uv run --no-sync --env-file .env langsmith dataset upload datasets/manual_qa_100.json \
  --name '设备手册RAG评测集100题-v1' \
  --description '20份PDF；排错35、保修免责30、步骤参数20、负向拒答15；零基页索引与逐字证据'
```

裁判配置放在项目根 `.env`。`JUDGE_MODEL` / `JUDGE_BASE_URL` 独立于被测模型；`JUDGE_API_KEY` 未设置时复用已有 `ARK_API_KEY` 或 `OPENAI_API_KEY`。当前配置为 `deepseek-v4-pro`、`https://ark.cn-beijing.volces.com/api/plan/v3`，并通过 `JUDGE_EXTRA_BODY={"thinking":{"type":"disabled"}}` 关闭该端点的深度思考。

完整评测：

```bash
uv run --no-sync python langsmith_eval.py \
  --metrics manual \
  --dataset-name '设备手册RAG评测集100题-v1' \
  --experiment-prefix '设备手册100题-DeepSeek裁判' \
  --max-concurrency 3 \
  --report-md reports/manual_qa_100_judge.md \
  --report-json reports/manual_qa_100_judge.json
```

`--limit N` 限制样本数，`--case-ids manual-011 manual-036 manual-066 manual-086` 选择四类小样本。`--retrieval-k` 设置 AP、Hit Rate、MRR 的 K；recall 和 faithfulness 始终使用完整实际上下文。

新实验保存在 LangSmith，每条完成的结果还会立即写入同名 `.jsonl`，全量完成后写 JSON/Markdown 汇总。需要对同一批实际回答重新打分时，使用 `--reuse-experiment-id`，不会重跑 RAG。

并发被测运行采用独立进程，隔离现有 Agent 的模块级 trace 和工具调用状态，并保留 LangSmith 父子 trace 关系。每个进程会加载嵌入模型，因此并发数需匹配内存；默认 1。被测端继续使用原有模型与完整 `chat_with_agent` 流程，联网搜索默认关闭。
