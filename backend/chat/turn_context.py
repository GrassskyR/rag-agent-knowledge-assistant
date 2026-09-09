from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class TurnContext:
    rag_context: dict | None = None
    step_queue: Any = None
    step_loop: Any = None
    web_sources: list[dict] = field(default_factory=list)
    web_results: list[dict] = field(default_factory=list)
    web_trace: dict = field(default_factory=dict)
    knowledge_calls: int = 0
    web_search_calls: int = 0
    web_fetch_calls: int = 0
    web_fetch_urls_used: int = 0
    lock: Any = field(default_factory=RLock)


_TURN_CONTEXT: ContextVar[TurnContext | None] = ContextVar("turn_context", default=None)


def get_turn_context() -> TurnContext:
    context = _TURN_CONTEXT.get()
    if context is None:
        context = TurnContext()
        _TURN_CONTEXT.set(context)
    return context


@contextmanager
def turn_scope():
    # 子任务和工具线程共享本轮对象，其他请求持有不同的对象。
    token = _TURN_CONTEXT.set(TurnContext())
    try:
        yield
    finally:
        _TURN_CONTEXT.reset(token)

_CURRENT_USER_QUERY: ContextVar[str] = ContextVar("current_user_query", default="")


def set_current_user_query(query: str):
    return _CURRENT_USER_QUERY.set(query or "")


def reset_current_user_query(token) -> None:
    _CURRENT_USER_QUERY.reset(token)


def get_current_user_query() -> str:
    return _CURRENT_USER_QUERY.get()
