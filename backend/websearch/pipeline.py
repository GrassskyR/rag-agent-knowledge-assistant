from typing import Annotated, List, Optional, TypedDict
import operator

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from backend.chat.streaming import (
    clear_sub_agent_group,
    emit_rag_step,
    set_sub_agent_group,
)
from backend.llm_utils import structured_invoke
from backend.websearch.client import (
    WEB_SEARCH_FETCH_TOP_N,
    WEB_SEARCH_TOP_K,
    WebSearchError,
    fetch_web_content,
    search_web,
)


class WebSearchState(TypedDict):
    query: str
    rewritten_query: Optional[str]
    results: List[dict]
    fetch_urls: List[str]
    fetched_pages: Annotated[List[dict], operator.add]
    web_sources: List[dict]
    web_trace: Optional[dict]
    fetch_decision: Optional[str]
    error: Optional[str]


class FetchDecision(BaseModel):
    should_fetch: bool = Field(description="是否需要打开搜索结果页面获取正文")
    urls: List[str] = Field(
        default_factory=list,
        description="需要 fetch 的 URL 列表，最多选择最可能有价值的页面",
    )
    reason: str = Field(default="", description="判断理由")


def _truncate(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _normalize_search_results(data: dict) -> List[dict]:
    raw_results = data.get("results") or []
    normalized: List[dict] = []
    for idx, item in enumerate(raw_results, 1):
        if not isinstance(item, dict):
            continue
        url = (item.get("url") or "").strip()
        if not url:
            continue
        normalized.append(
            {
                "filename": item.get("title") or url,
                "title": item.get("title") or url,
                "url": url,
                "text": item.get("description") or "",
                "source": item.get("source") or "",
                "engine": item.get("engine") or "",
                "source_type": "web",
                "rrf_rank": idx,
            }
        )
    return normalized


def rewrite_query_node(state: WebSearchState) -> WebSearchState:
    """让子 agent 把用户原始提问提炼成精简搜索关键词；失败回退原 query。"""
    original = state["query"]
    emit_rag_step("✏️", "正在提炼搜索关键词...", original[:80])
    prompt = (
        "请把下面这条用户提问改写为「一个」适合搜索引擎的精简关键词串，要求：\n"
        "- 解析代词/指代，去掉寒暄与废话；\n"
        "- 保留关键实体（人名/产品名/术语/时间等）；\n"
        "- 中英文均可，控制在 30 字以内；\n"
        "- 不要引号、不要解释、只输出关键词本身。\n\n"
        f"用户提问：{original}"
    )
    try:
        from backend.chat.runtime import fast_model

        rewritten = (fast_model.invoke([{"role": "user", "content": prompt}]).content or "").strip()
        if not rewritten:
            rewritten = original
    except Exception:
        rewritten = original

    emit_rag_step("✅", "搜索关键词已提炼", rewritten[:80])
    trace = state.get("web_trace") or {}
    trace.update({
        "web_original_query": original,
        "web_rewritten_query": rewritten,
    })
    return {"rewritten_query": rewritten, "web_trace": trace}


def search_node(state: WebSearchState) -> WebSearchState:
    query = state.get("rewritten_query") or state["query"]
    emit_rag_step("🔎", "正在联网搜索...", f"查询: {query[:80]}")
    try:
        data = search_web(query, limit=WEB_SEARCH_TOP_K)
    except WebSearchError as exc:
        message = str(exc)
        emit_rag_step("⚠️", "联网搜索失败", message[:120])
        return {"error": message, "results": [], "web_sources": []}

    results = _normalize_search_results(data)
    engines = data.get("engines") or []
    detail = f"结果 {len(results)} 条"
    if engines:
        detail += f"，引擎: {', '.join(engines)}"
    emit_rag_step("✅", "联网搜索完成", detail)
    trace = state.get("web_trace") or {}
    trace.update({
        "web_search_used": True,
        "web_query": query,
        "web_results": results,
        "web_result_count": len(results),
        "web_engines": engines,
        "web_partial_failures": data.get("partialFailures") or [],
    })
    return {
        "results": results,
        "web_sources": results,
        "web_trace": trace,
    }


def decide_fetch_node(state: WebSearchState) -> WebSearchState:
    results = state.get("results") or []
    if not results:
        return {"fetch_urls": [], "fetch_decision": "no_results"}

    emit_rag_step("🧭", "正在判断是否需要打开网页...", "")
    candidates = [
        {
            "title": item.get("title") or item.get("filename"),
            "url": item.get("url"),
            "description": item.get("text", ""),
        }
        for item in results[:WEB_SEARCH_TOP_K]
    ]
    prompt = (
        "你是一个联网检索子 Agent。根据用户问题和搜索结果摘要，判断是否需要打开网页正文。\n"
        "如果搜索摘要已经足够回答，should_fetch=false。\n"
        "如果需要更完整、精确或可引用的事实，should_fetch=true，并选择最多 "
        f"{WEB_SEARCH_FETCH_TOP_N} 个最有价值的 URL。\n\n"
        f"用户问题：{state['query']}\n"
        f"搜索结果：{candidates}"
    )
    try:
        from backend.chat.runtime import fast_model

        decision = structured_invoke(
            fast_model, FetchDecision, [{"role": "user", "content": prompt}]
        )
        allowed_urls = {item.get("url") for item in results}
        urls = [
            url
            for url in (decision.urls or [])
            if url in allowed_urls
        ][:WEB_SEARCH_FETCH_TOP_N]
        if not decision.should_fetch:
            urls = []
        reason = (decision.reason or "").strip()
    except Exception:
        urls = [item["url"] for item in results[:1]]
        reason = "decision_model_error_fetch_first_result"

    if urls:
        emit_rag_step("📄", f"需要获取 {len(urls)} 个网页正文", reason[:120])
    else:
        emit_rag_step("✅", "搜索摘要足够，跳过网页正文获取", reason[:120])

    trace = state.get("web_trace") or {}
    trace.update({
        "web_fetch_decision": reason or ("fetch" if urls else "skip"),
        "web_fetch_urls": urls,
    })
    return {"fetch_urls": urls, "fetch_decision": reason, "web_trace": trace}


def fetch_pages_node(state: WebSearchState) -> WebSearchState:
    fetched_pages: List[dict] = []
    for url in state.get("fetch_urls") or []:
        emit_rag_step("🌐", "正在读取网页正文...", url[:120])
        try:
            data = fetch_web_content(url)
        except WebSearchError as exc:
            emit_rag_step("⚠️", "网页正文读取失败", str(exc)[:120])
            continue
        content = _truncate(data.get("content") or "", 6000)
        fetched_pages.append({
            "url": data.get("finalUrl") or data.get("url") or url,
            "title": data.get("title") or url,
            "content": content,
            "content_type": data.get("contentType") or "",
            "retrieval_method": data.get("retrievalMethod") or "",
            "truncated": bool(data.get("truncated")),
        })
    if fetched_pages:
        emit_rag_step("✅", f"网页正文读取完成，共 {len(fetched_pages)} 个页面", "")
    return {"fetched_pages": fetched_pages}


def synthesis_node(state: WebSearchState) -> WebSearchState:
    sources = [dict(item) for item in (state.get("results") or [])]
    by_url = {item.get("url"): item for item in sources if item.get("url")}
    for page in state.get("fetched_pages") or []:
        url = page.get("url")
        if not url:
            continue
        target = by_url.get(url)
        if target is None:
            target = {
                "filename": page.get("title") or url,
                "title": page.get("title") or url,
                "url": url,
                "source_type": "web",
                "rrf_rank": len(sources) + 1,
            }
            sources.append(target)
            by_url[url] = target
        if page.get("content"):
            target["text"] = page["content"]
            target["fetched"] = True

    for idx, source in enumerate(sources, 1):
        source["rrf_rank"] = idx

    trace = state.get("web_trace") or {}
    trace.update({
        "web_sources": sources,
        "web_fetched_pages": state.get("fetched_pages") or [],
        "web_fetch_count": len(state.get("fetched_pages") or []),
    })
    return {"web_sources": sources, "web_trace": trace}


def build_web_search_graph():
    graph = StateGraph(WebSearchState)
    graph.add_node("rewrite_query", rewrite_query_node)
    graph.add_node("search", search_node)
    graph.add_node("decide_fetch", decide_fetch_node)
    graph.add_node("fetch_pages", fetch_pages_node)
    graph.add_node("synthesis", synthesis_node)

    graph.set_entry_point("rewrite_query")
    graph.add_edge("rewrite_query", "search")
    graph.add_edge("search", "decide_fetch")
    graph.add_edge("decide_fetch", "fetch_pages")
    graph.add_edge("fetch_pages", "synthesis")
    graph.add_edge("synthesis", END)
    return graph.compile()


_web_search_graph = build_web_search_graph()


def run_web_search_graph(query: str) -> dict:
    set_sub_agent_group("Web Search")
    try:
        result = _web_search_graph.invoke({
            "query": query,
            "rewritten_query": None,
            "results": [],
            "fetch_urls": [],
            "fetched_pages": [],
            "web_sources": [],
            "web_trace": None,
            "fetch_decision": None,
            "error": None,
        })
    finally:
        clear_sub_agent_group()
    return result
