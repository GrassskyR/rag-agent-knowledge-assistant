"""单轮对话内 web 检索 trace 累加器。

web_search 建立编号、web_fetch 按 url 合并摘要，统一累积到同一 trace，
避免 record_rag_context 整体覆盖导致后写覆盖前写、web_sources 缺源 / [n] 错位。
状态绑定当前请求，工具线程共享本轮上下文。
"""
from typing import Optional

from backend.chat.turn_context import get_turn_context


def reset_web_context() -> None:
    """每轮对话开始时重置 web 累加状态。"""
    context = get_turn_context()
    context.web_sources = []
    context.web_results = []
    context.web_trace = {}


def _next_rank() -> int:
    return len(get_turn_context().web_sources) + 1


def add_search_results(query: str, results: list[dict], engines: list) -> list[dict]:
    """追加搜索结果并统一分配连续编号 [n]（rrf_rank）。按 url 去重，跳过已存在。

    返回本次新增的带编号条目（供工具格式化返回给主 agent）。
    """
    context = get_turn_context()
    numbered: list[dict] = []
    for item in results or []:
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        if any((s.get("url") or "") == url for s in context.web_sources):
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
        context.web_sources.append(entry)
        # 原始摘要快照（独立 dict，fetch 合并 summary 时不会污染）
        context.web_results.append(dict(entry))
        numbered.append(entry)

    context.web_trace.update({
        "web_search_used": True,
        "web_query": query,
        "web_results": context.web_results,
        "web_result_count": len(context.web_sources),
        "web_engines": engines or context.web_trace.get("web_engines") or [],
    })
    return numbered


def add_fetched_page(url: str, title: str, summary: str) -> None:
    """按 url 合并摘要到对应 web_sources 条目（fetched=True, text=summary）。

    url 不在已有条目中则追加新条目（分配新编号），保证主 agent 看到的 [n] 与
    最终 web_sources rrf_rank 一致。
    """
    if not url:
        return
    context = get_turn_context()
    entry = next((s for s in context.web_sources if (s.get("url") or "") == url), None)
    if entry is None:
        entry = {
            "filename": title or url,
            "title": title or url,
            "url": url,
            "source_type": "web",
            "rrf_rank": _next_rank(),
            "fetched": False,
        }
        context.web_sources.append(entry)
    entry["fetched"] = True
    entry["text"] = summary

    fetched_pages = [dict(p) for p in (context.web_trace.get("web_fetched_pages") or [])]
    fetched_pages = [p for p in fetched_pages if (p.get("url") or "") != url]
    fetched_pages.append({"url": url, "title": title or url, "content": summary})
    context.web_trace["web_fetched_pages"] = fetched_pages
    context.web_trace["web_fetch_count"] = len(fetched_pages)


def get_rank_for_url(url: str) -> Optional[int]:
    """查询 url 对应的统一编号（rrf_rank），供 web_fetch 返回字符串对齐 [n]。"""
    for s in get_turn_context().web_sources:
        if (s.get("url") or "") == url:
            return s.get("rrf_rank")
    return None


def flush_web_context_to_rag() -> None:
    """把当前累积的 web trace 整体写入本轮 RAG 上下文（每次工具调用后调用）。

    record_rag_context 是整体覆盖，但此处每次 flush 写入的都是完整累积状态，
    因此多次 flush 不会丢源；中途异常也有已 flush 的 trace。
    """
    context = get_turn_context()
    if not context.web_sources and not context.web_trace:
        return
    from backend.chat.rag_context import record_rag_context

    trace = {
        "tool_used": True,
        "tool_name": "web_search",
        "web_sources": [dict(s) for s in context.web_sources],
    }
    trace.update(context.web_trace)
    record_rag_context(trace)
