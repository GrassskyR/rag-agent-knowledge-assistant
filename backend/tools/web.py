"""主 agent 可独立调用的联网工具：web_search / web_fetch。

- web_search：返回编号列表（标题+摘要+URL），不抓正文。
- web_fetch：用 Playwright 微服务打开链接，fast_model 围绕用户问题做要点摘要后返回；
  长正文永不进入主 agent 上下文，防止污染。

按工具分别限额的轮内计数器（沿用 knowledge.py 的 reset_* 模式，service 每轮重置）。
"""
import os

from langchain_core.tools import tool
from langsmith import traceable


def _read_positive_int_env(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default))), 1)
    except ValueError:
        return default


WEB_SEARCH_MAX_CALLS = _read_positive_int_env("WEB_SEARCH_MAX_CALLS", 2)
WEB_FETCH_MAX_CALLS = _read_positive_int_env("WEB_FETCH_MAX_CALLS", 3)
WEB_FETCH_MAX_URLS = _read_positive_int_env("WEB_FETCH_MAX_URLS", 5)

_WEB_SEARCH_CALLS = 0
_WEB_FETCH_CALLS = 0
_WEB_FETCH_URLS_USED = 0


def reset_web_tool_calls() -> None:
    """每轮对话开始时重置 web 工具调用计数。"""
    global _WEB_SEARCH_CALLS, _WEB_FETCH_CALLS, _WEB_FETCH_URLS_USED
    _WEB_SEARCH_CALLS = 0
    _WEB_FETCH_CALLS = 0
    _WEB_FETCH_URLS_USED = 0


def _try_acquire_web_search_call() -> bool:
    global _WEB_SEARCH_CALLS
    if _WEB_SEARCH_CALLS >= WEB_SEARCH_MAX_CALLS:
        return False
    _WEB_SEARCH_CALLS += 1
    return True


def _try_acquire_web_fetch_call() -> tuple[bool, int]:
    """返回 (是否允许, 剩余 URL 预算)。"""
    global _WEB_FETCH_CALLS
    if _WEB_FETCH_CALLS >= WEB_FETCH_MAX_CALLS:
        return False, 0
    _WEB_FETCH_CALLS += 1
    remaining = max(WEB_FETCH_MAX_URLS - _WEB_FETCH_URLS_USED, 0)
    return True, remaining


_SUMMARY_PROMPT = (
    "你是联网检索子 Agent。下面给你一段网页正文与用户的原始问题。\n"
    "请围绕用户问题，从正文中提取 3-8 条可引用的关键要点：\n"
    "- 用编号列表，每条一句话，包含可引用的事实/数据/结论；\n"
    "- 只提取与问题相关的信息，忽略无关内容；\n"
    "- 若正文与问题无关或无可用信息，只输出一行：「无相关内容」。\n\n"
    "用户问题：{question}\n\n"
    "网页正文：\n{content}\n\n"
    "要点："
)


@traceable
def _summarize_for_query(model, content: str, question: str) -> str:
    """围绕用户问题对网页正文做要点摘要（纯文本 invoke，避开结构化输出兼容问题）。"""
    if not (content or "").strip():
        return "无相关内容"
    prompt = _SUMMARY_PROMPT.format(
        question=question or "(未提供)",
        content=content[:8000],
    )
    try:
        resp = model.invoke([{"role": "user", "content": prompt}])
        text = (getattr(resp, "content", resp) or "").strip()
        return text or "无相关内容"
    except Exception as exc:
        return f"摘要失败：{exc}"


def _format_search_results(numbered: list[dict]) -> str:
    formatted = []
    for item in numbered:
        rank = item.get("rrf_rank")
        title = item.get("title") or item.get("url")
        url = item.get("url") or ""
        snippet = item.get("text") or ""
        engine = item.get("engine") or ""
        meta = "Web" + (f", {engine}" if engine else "")
        formatted.append(f"[{rank}] {title} - {url} ({meta}):\n{snippet}")
    return "Web Search Results:\n" + "\n\n---\n\n".join(formatted)


@tool("web_search")
@traceable
def web_search(query: str) -> str:
    """Search the live web for current/external information. Returns numbered results
    (title + snippet + url). To read a page's content, call web_fetch with the urls you want.
    Cite sources using the returned [n] numbers."""
    if not _try_acquire_web_search_call():
        return (
            f"TOOL_CALL_LIMIT_REACHED: web_search has already been called "
            f"{WEB_SEARCH_MAX_CALLS} times in this turn. Use the existing results "
            f"and provide the final answer directly."
        )

    from backend.chat.streaming import clear_sub_agent_group, emit_rag_step, set_sub_agent_group
    from backend.chat.web_context import add_search_results, flush_web_context_to_rag
    from backend.websearch.client import WebSearchError, search_web
    from backend.websearch.pipeline import _normalize_search_results

    set_sub_agent_group("Web Search")
    try:
        emit_rag_step("🔎", "正在联网搜索...", query[:80])
        try:
            data = search_web(query)
        except WebSearchError as exc:
            emit_rag_step("⚠️", "联网搜索失败", str(exc)[:120])
            flush_web_context_to_rag()
            return f"Web search failed: {exc}"
    finally:
        clear_sub_agent_group()

    results = _normalize_search_results(data)
    engines = data.get("engines") or []
    numbered = add_search_results(query, results, engines)
    flush_web_context_to_rag()

    detail = f"结果 {len(numbered)} 条"
    if engines:
        detail += f"，引擎: {', '.join(engines)}"
    emit_rag_step("✅", "联网搜索完成", detail)

    if not numbered:
        return "No web results found. Try refining the query or answer from your own knowledge."
    return _format_search_results(numbered)


@tool("web_fetch")
@traceable
def web_fetch(urls: list) -> str:
    """Open web pages with a headless browser and return concise bullet summaries,
    each keyed by its [n] number, focused on the user's question. Pass 1-3 urls from
    web_search results. Cite using the returned [n] numbers."""
    if not isinstance(urls, list) or not urls:
        return "web_fetch received no urls. Pass a list of urls from web_search results."

    allowed, remaining = _try_acquire_web_fetch_call()
    if not allowed:
        return (
            f"TOOL_CALL_LIMIT_REACHED: web_fetch has already been called "
            f"{WEB_FETCH_MAX_CALLS} times in this turn. Use the gathered summaries "
            f"and provide the final answer directly."
        )

    global _WEB_FETCH_URLS_USED

    urls = [u for u in urls if isinstance(u, str) and u.strip()]
    if remaining == 0:
        return (
            f"TOOL_CALL_LIMIT_REACHED: cumulative url budget ({WEB_FETCH_MAX_URLS}) "
            f"reached this turn. Use the gathered summaries and provide the final answer directly."
        )
    if len(urls) > remaining:
        urls = urls[:remaining]
    _WEB_FETCH_URLS_USED += len(urls)

    from backend.chat.runtime import fast_model
    from backend.chat.streaming import clear_sub_agent_group, emit_rag_step, set_sub_agent_group
    from backend.chat.turn_context import get_current_user_query
    from backend.chat.web_context import add_fetched_page, flush_web_context_to_rag, get_rank_for_url
    from backend.websearch.client import WebSearchError, fetch_web_content_pw

    user_query = get_current_user_query()

    set_sub_agent_group("Web Fetch")
    summaries: list[tuple[int, str, str, str]] = []
    try:
        for url in urls:
            emit_rag_step("🌐", "正在读取网页正文...", url[:120])
            try:
                data = fetch_web_content_pw(url)
            except WebSearchError as exc:
                emit_rag_step("⚠️", "网页正文读取失败", str(exc)[:120])
                continue
            content = data.get("content") or ""
            title = data.get("title") or url
            emit_rag_step("🧠", "正在提炼要点...", (title or url)[:80])
            summary = _summarize_for_query(fast_model, content, user_query)
            add_fetched_page(url, title, summary)
            rank = get_rank_for_url(url)
            summaries.append((rank, url, title, summary))
    finally:
        clear_sub_agent_group()

    flush_web_context_to_rag()

    if not summaries:
        return "No pages could be fetched. Try other urls or answer from search snippets."

    formatted = []
    for rank, url, title, summary in summaries:
        formatted.append(f"[{rank}] {title} - {url}\n要点：\n{summary}")
    emit_rag_step("✅", f"网页要点读取完成，共 {len(summaries)} 个页面", "")
    return "\n\n---\n\n".join(formatted)
