"""Playwright 无头浏览器抓取微服务。

绕过普通 HTTP 请求被部分网站拦截的问题。单一 browser 实例（lifespan 管理），
每请求新建 context（真实桌面 UA、zh-CN、禁用自动化特征、viewport），
`page.goto(wait_until="domcontentloaded")` + `networkidle` 软超时，`finally` 关 context。

返回信封复用 open-websearch 结构，使后端 client 的 `_unwrap_envelope` 零改动复用。
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from playwright.async_api import Browser, async_playwright
from pydantic import BaseModel

from extract import extract_content

_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

_browser: Optional[Browser] = None
_semaphore: Optional[asyncio.Semaphore] = None


class FetchRequest(BaseModel):
    url: str
    maxChars: int = 30000
    navTimeoutMs: int = 5000


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _browser, _semaphore
    _semaphore = asyncio.Semaphore(4)
    pw = await async_playwright().start()
    _browser = await pw.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    try:
        yield
    finally:
        if _browser is not None:
            await _browser.close()
        await pw.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "data": {"ready": _browser is not None}}


@app.post("/fetch")
async def fetch(req: FetchRequest):
    if _browser is None or _semaphore is None:
        return {"status": "error", "error": {"message": "browser not ready"}}
    async with _semaphore:
        try:
            content, final_url, title, truncated = await _fetch_page(req)
        except Exception as exc:
            return {"status": "error", "error": {"message": str(exc)}}

    return {
        "status": "ok",
        "data": {
            "url": req.url,
            "finalUrl": final_url or req.url,
            "title": title or req.url,
            "content": content,
            "contentType": "text/html",
            "retrievalMethod": "playwright",
            "truncated": truncated,
        },
    }


async def _fetch_page(req: FetchRequest) -> tuple[str, str, str, bool]:
    context = await _browser.new_context(
        user_agent=_DESKTOP_UA,
        locale="zh-CN",
        viewport={"width": 1366, "height": 900},
        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    page = await context.new_page()
    try:
        await page.goto(req.url, wait_until="domcontentloaded", timeout=req.navTimeoutMs)
        try:
            await page.wait_for_load_state("networkidle", timeout=req.navTimeoutMs)
        except Exception:
            pass  # networkidle 软超时：domcontentloaded 后即可继续
        html = await page.content()
        final_url = page.url
        title = await page.title()
    finally:
        await context.close()

    content, truncated = extract_content(html, req.url, req.maxChars)
    return content, final_url, title, truncated
