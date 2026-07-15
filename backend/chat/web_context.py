"""单轮对话内 web 检索 trace 累加器。

web_search 建立编号、web_fetch 按 url 合并摘要，统一累积到同一 trace，
避免 record_rag_context 整体覆盖导致后写覆盖前写、web_sources 缺源 / [n] 错位。
模式同 turn_context / rag_context：模块级暂存，service 每轮 reset。
"""
from typing import Optional

# 最终 web_sources：按 url 去重的条目，fetch 时合并 text=fetched
_web_sources: list[dict] = []
# 搜索原始摘要快照（text=snippet，fetch 不改它），用于 trace 的 web_results
_web_results_raw: list[dict] = []
_web_trace: dict = {}


def reset_web_context() -> None:
    """每轮对话开始时重置 web 累加状态。"""
    global _web_sources, _web_results_raw, _web_trace
    _web_sources = []
    _web_results_raw = []
    _web_trace = {}


def _next_rank() -> int:
    return len(_web_sources) + 1


def add_search_results(query: str, results: list[dict], engines: list) -> list[dict]:
    """追加搜索结果并统一分配连续编号 [n]（rrf_rank）。按 url 去重，跳过已存在。

    返回本次新增的带编号条目（供工具格式化返回给主 agent）。
    """
    numbered: list[dict] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        if any((s.get("url") or "") == url for s in _web_sources):
            continue
        rank = _next_rank()
        entry = {
            "filename": item.get("title") or url,
            "title": item.get("title") or url,
            "url": url,
            "text": item.get("text") or item.get("description") or "",
            "source": item.get("source") or "",
            "engine": item.get("engine") or "",
            "source_type": "web",
            "rrf_rank": rank,
            "fetched": False,
        }
        _web_sources.append(entry)
        # 原始摘要快照（独立 dict，fetch 合并 summary 时不会污染）
        _web_results_raw.append(dict(entry))
        numbered.append(entry)

    _web_trace.update({
        "web_search_used": True,
        "web_query": query,
        "web_results": _web_results_raw,
        "web_result_count": len(_web_sources),
        "web_engines": engines or _web_trace.get("web_engines") or [],
    })
    return numbered


def add_fetched_page(url: str, title: str, summary: str) -> None:
    """按 url 合并摘要到对应 web_sources 条目（fetched=True, text=summary）。

    url 不在已有条目中则追加新条目（分配新编号），保证主 agent 看到的 [n] 与
    最终 web_sources rrf_rank 一致。
    """
    if not url:
        return
    entry = next((s for s in _web_sources if (s.get("url") or "") == url), None)
    if entry is None:
        entry = {
            "filename": title or url,
            "title": title or url,
            "url": url,
            "source_type": "web",
            "rrf_rank": _next_rank(),
            "fetched": False,
        }
        _web_sources.append(entry)
    entry["fetched"] = True
    entry["text"] = summary

    fetched_pages = [dict(p) for p in (_web_trace.get("web_fetched_pages") or [])]
    fetched_pages = [p for p in fetched_pages if (p.get("url") or "") != url]
    fetched_pages.append({"url": url, "title": title or url, "content": summary})
    _web_trace["web_fetched_pages"] = fetched_pages
    _web_trace["web_fetch_count"] = len(fetched_pages)


def get_rank_for_url(url: str) -> Optional[int]:
    """查询 url 对应的统一编号（rrf_rank），供 web_fetch 返回字符串对齐 [n]。"""
    for s in _web_sources:
        if (s.get("url") or "") == url:
            return s.get("rrf_rank")
    return None


def flush_web_context_to_rag() -> None:
    """把当前累积的 web trace 整体写入 _LAST_RAG_CONTEXT（每次工具调用后调用）。

    record_rag_context 是整体覆盖，但此处每次 flush 写入的都是完整累积状态，
    因此多次 flush 不会丢源；中途异常也有已 flush 的 trace。
    """
    if not _web_sources and not _web_trace:
        return
    from backend.chat.rag_context import record_rag_context

    trace = {
        "tool_used": True,
        "tool_name": "web_search",
        "web_sources": [dict(s) for s in _web_sources],
    }
    trace.update(_web_trace)
    record_rag_context(trace)
