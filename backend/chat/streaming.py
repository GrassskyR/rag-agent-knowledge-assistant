"""RAG 检索步骤的 SSE 实时推送（跨线程安全，供 rag pipeline 在 worker 线程中调用）。"""

import asyncio
from contextvars import ContextVar

from backend.chat.turn_context import get_turn_context

_sub_agent_group: ContextVar[str | None] = ContextVar("sub_agent_group", default=None)


def set_rag_step_queue(queue) -> None:
    """设置 RAG 步骤队列，并捕获当前事件循环以便跨线程调度。"""
    context = get_turn_context()
    context.step_queue = queue
    if queue:
        try:
            context.step_loop = asyncio.get_running_loop()
        except RuntimeError:
            context.step_loop = asyncio.get_event_loop()
    else:
        context.step_loop = None


def set_sub_agent_group(group: str) -> None:
    """设置当前执行上下文的子 Agent 分组标识。"""
    _sub_agent_group.set(group)


def clear_sub_agent_group() -> None:
    """清除当前执行上下文的子 Agent 分组标识。"""
    _sub_agent_group.set(None)


def get_sub_agent_group():
    """获取当前线程的子 Agent 分组标识。"""
    return _sub_agent_group.get()


def emit_rag_step(icon: str, label: str, detail: str = "") -> None:
    """向队列发送一个 RAG 检索步骤。支持跨线程安全调用。"""
    context = get_turn_context()
    queue, loop = context.step_queue, context.step_loop
    if queue is not None and loop is not None:
        step = {"icon": icon, "label": label, "detail": detail}
        group = get_sub_agent_group()
        if group:
            step["group"] = group
        try:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, step)
        except Exception:
            pass
