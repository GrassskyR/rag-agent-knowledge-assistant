from contextvars import ContextVar

_CURRENT_USER_QUERY: ContextVar[str] = ContextVar("current_user_query", default="")


def set_current_user_query(query: str):
    return _CURRENT_USER_QUERY.set(query or "")


def reset_current_user_query(token) -> None:
    _CURRENT_USER_QUERY.reset(token)


def get_current_user_query() -> str:
    return _CURRENT_USER_QUERY.get()
