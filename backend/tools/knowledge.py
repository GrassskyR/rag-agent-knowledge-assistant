from langchain_core.tools import tool
from langsmith import traceable
_KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0


def reset_knowledge_tool_calls() -> None:
    """每轮对话开始时重置知识库工具调用计数。"""
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN = 0


def _try_acquire_knowledge_tool_call() -> bool:
    global _KNOWLEDGE_TOOL_CALLS_THIS_TURN
    if _KNOWLEDGE_TOOL_CALLS_THIS_TURN >= 1:
        return False
    _KNOWLEDGE_TOOL_CALLS_THIS_TURN += 1
    return True


_GRADE_PROMPT = (
    "You are a grader assessing relevance of retrieved context to a user question.\n\n"
    "Retrieved context:\n{context}\n\n"
    "User question: {question}\n\n"
    "If the context contains enough information to answer the question, grade it as 'yes'. "
    "If it is missing, weakly related, or cannot answer the question, grade it as 'no'."
)


def _format_knowledge_docs(docs: list[dict]) -> str:
    formatted = []
    for i, result in enumerate(docs, 1):
        source = result.get("filename", "Unknown")
        page = result.get("page_number", "N/A")
        text = result.get("text", "")
        formatted.append(f"[{i}] {source} (Page {page}):\n{text}")
    return "Retrieved Chunks:\n" + "\n\n---\n\n".join(formatted)


def _format_web_sources(sources: list[dict]) -> str:
    formatted = []
    for i, source in enumerate(sources, 1):
        title = source.get("title") or source.get("filename") or source.get("url") or "Unknown"
        url = source.get("url") or ""
        text = source.get("text") or ""
        engine = source.get("engine") or ""
        meta = "Web"
        if engine:
            meta += f", {engine}"
        header = f"[{i}] {title}"
        if url:
            header += f" - {url}"
        formatted.append(f"{header} ({meta}):\n{text}")
    return "Web Search Sources:\n" + "\n\n---\n\n".join(formatted)


def _is_rag_sufficient(query: str, rag_result: dict) -> tuple[bool, str]:
    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    if not docs:
        return False, "no_relevant_rag_documents"

    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}
    score = str(rag_trace.get("grade_score") or "").strip().lower()
    if score == "yes":
        return True, "rag_grade_passed"
    if score == "no" and rag_trace.get("retrieval_stage") == "initial":
        return False, "initial_rag_grade_failed"

    try:
        from backend.chat.runtime import fast_model
        from backend.rag.pipeline import extract_grade_score

        context = rag_result.get("context", "")
        if not context:
            return False, "empty_rag_context"
        response = fast_model.invoke(
            [{
                "role": "user",
                "content": (
                    _GRADE_PROMPT.format(question=query, context=context)
                    + '\nReturn only JSON: {"binary_score":"yes"} or {"binary_score":"no"}.'
                ),
            }]
        )
        final_score = extract_grade_score(getattr(response, "content", response))
    except Exception:
        return True, "grader_unavailable_assume_rag_sufficient"

    if not final_score:
        return True, "grader_unavailable_assume_rag_sufficient"
    if final_score == "yes":
        return True, "final_rag_grade_passed"
    return False, "final_rag_grade_failed"


@tool("search_knowledge_base")
@traceable
def search_knowledge_base(query: str) -> str:
    """Search for information in the knowledge base using hybrid retrieval (dense + sparse vectors)."""
    if not _try_acquire_knowledge_tool_call():
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_base has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )

    from backend.chat.rag_context import record_rag_context
    from backend.rag.pipeline import run_rag_graph

    rag_result = run_rag_graph(query)

    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}
    record_rag_context(rag_trace)

    if not docs:
        return "No relevant documents found in the knowledge base."

    return _format_knowledge_docs(docs)


@tool("search_knowledge_with_web_fallback")
@traceable
def search_knowledge_with_web_fallback(query: str) -> str:
    """
    Search the knowledge base first. Only if the knowledge base is insufficient,
    supplement with live web search and optional web page fetching.
    """
    if not _try_acquire_knowledge_tool_call():
        return (
            "TOOL_CALL_LIMIT_REACHED: search_knowledge_with_web_fallback has already been called once in this turn. "
            "Use the existing retrieval result and provide the final answer directly."
        )

    from backend.chat.rag_context import record_rag_context
    from backend.chat.turn_context import get_current_user_query
    from backend.rag.pipeline import run_rag_graph

    rag_result = run_rag_graph(query)
    docs = rag_result.get("docs", []) if isinstance(rag_result, dict) else []
    rag_trace = rag_result.get("rag_trace", {}) if isinstance(rag_result, dict) else {}
    rag_trace["tool_name"] = "search_knowledge_with_web_fallback"

    rag_sufficient, reason = _is_rag_sufficient(query, rag_result)
    rag_trace["rag_fallback_reason"] = reason

    if rag_sufficient:
        record_rag_context(rag_trace)
        if not docs:
            return "No relevant documents found in the knowledge base."
        return _format_knowledge_docs(docs)

    from backend.websearch import run_web_search_graph

    web_query = get_current_user_query() or query
    web_result = run_web_search_graph(web_query)
    web_sources = web_result.get("web_sources", []) if isinstance(web_result, dict) else []
    web_trace = web_result.get("web_trace", {}) if isinstance(web_result, dict) else {}

    combined_trace = {
        **rag_trace,
        **web_trace,
        "tool_used": True,
        "tool_name": "search_knowledge_with_web_fallback",
        "tool_query": query,
        "rag_fallback_reason": reason,
    }
    record_rag_context(combined_trace)

    if web_sources:
        return _format_web_sources(web_sources)

    if docs:
        return (
            "Knowledge base retrieval was insufficient and web search returned no usable sources. "
            "Use the weak knowledge base result cautiously:\n\n"
            + _format_knowledge_docs(docs)
        )
    return "No relevant documents found in the knowledge base, and web search returned no usable sources."
