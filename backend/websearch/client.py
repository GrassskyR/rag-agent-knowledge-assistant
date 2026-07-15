import os
from typing import Any

import httpx
from langsmith import traceable


def _read_positive_int_env(name: str, default: int) -> int:
    try:
        return max(int(os.getenv(name, str(default))), 1)
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


WEB_SEARCH_BASE_URL = os.getenv("WEB_SEARCH_BASE_URL", "http://127.0.0.1:3210").rstrip("/")
WEB_SEARCH_TIMEOUT = _read_float_env("WEB_SEARCH_TIMEOUT", 20.0)
WEB_SEARCH_TOP_K = _read_positive_int_env("WEB_SEARCH_TOP_K", 5)
WEB_SEARCH_FETCH_TOP_N = _read_positive_int_env("WEB_SEARCH_FETCH_TOP_N", 2)
WEB_SEARCH_FETCH_MAX_CHARS = _read_positive_int_env("WEB_SEARCH_FETCH_MAX_CHARS", 30000)
# Playwright 抓取微服务（绕过反爬拦截）
WEB_FETCH_BASE_URL = os.getenv("WEB_FETCH_BASE_URL", "http://127.0.0.1:3220").rstrip("/")
WEB_FETCH_TIMEOUT = _read_float_env("WEB_FETCH_TIMEOUT", 30.0)
WEB_FETCH_NAV_TIMEOUT_MS = _read_positive_int_env("WEB_FETCH_NAV_TIMEOUT_MS", 5000)
WEB_SEARCH_MODE = os.getenv("WEB_SEARCH_MODE", "").strip()
WEB_SEARCH_ENGINES = [
    item.strip()
    for item in os.getenv("WEB_SEARCH_ENGINES", "").split(",")
    if item.strip()
]


class WebSearchError(RuntimeError):
    pass


def _unwrap_envelope(payload: dict[str, Any], operation: str) -> Any:
    if payload.get("status") == "ok":
        return payload.get("data")
    error = payload.get("error") or {}
    message = error.get("message") or payload.get("hint") or f"{operation} failed"
    raise WebSearchError(message)


def check_status() -> dict[str, Any]:
    try:
        with httpx.Client(timeout=WEB_SEARCH_TIMEOUT, trust_env=False) as client:
            response = client.get(f"{WEB_SEARCH_BASE_URL}/status")
            response.raise_for_status()
            data = _unwrap_envelope(response.json(), "status")
            return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        raise WebSearchError(f"open-websearch daemon unavailable: {exc}") from exc


@traceable
def search_web(query: str, limit: int | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {
        "query": query,
        "limit": limit or WEB_SEARCH_TOP_K,
    }
    if WEB_SEARCH_ENGINES:
        body["engines"] = WEB_SEARCH_ENGINES
    if WEB_SEARCH_MODE:
        body["searchMode"] = WEB_SEARCH_MODE

    try:
        with httpx.Client(timeout=WEB_SEARCH_TIMEOUT, trust_env=False) as client:
            response = client.post(f"{WEB_SEARCH_BASE_URL}/search", json=body)
            response.raise_for_status()
            data = _unwrap_envelope(response.json(), "search")
            return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        raise WebSearchError(f"web search failed: {exc}") from exc


@traceable
def fetch_web_content(url: str, max_chars: int | None = None) -> dict[str, Any]:
    try:
        with httpx.Client(timeout=WEB_SEARCH_TIMEOUT, trust_env=False) as client:
            response = client.post(
                f"{WEB_SEARCH_BASE_URL}/fetch-web",
                json={
                    "url": url,
                    "maxChars": max_chars or WEB_SEARCH_FETCH_MAX_CHARS,
                    "readability": True,
                },
            )
            response.raise_for_status()
            data = _unwrap_envelope(response.json(), "fetch-web")
            return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        raise WebSearchError(f"web fetch failed: {exc}") from exc


@traceable
def fetch_web_content_pw(url: str, max_chars: int | None = None) -> dict[str, Any]:
    """通过 Playwright 无头浏览器微服务抓取网页正文，绕过反爬拦截。

    返回信封结构与 fetch_web_content 一致（复用 _unwrap_envelope），
    供 web_fetch 工具调用；原 fetch_web_content 保留给 fallback 子图。
    """
    try:
        with httpx.Client(timeout=WEB_FETCH_TIMEOUT, trust_env=False) as client:
            response = client.post(
                f"{WEB_FETCH_BASE_URL}/fetch",
                json={
                    "url": url,
                    "maxChars": max_chars or WEB_SEARCH_FETCH_MAX_CHARS,
                    "navTimeoutMs": WEB_FETCH_NAV_TIMEOUT_MS,
                },
            )
            response.raise_for_status()
            data = _unwrap_envelope(response.json(), "fetch-web")
            return data if isinstance(data, dict) else {}
    except httpx.HTTPError as exc:
        raise WebSearchError(f"web fetch (playwright) failed: {exc}") from exc
