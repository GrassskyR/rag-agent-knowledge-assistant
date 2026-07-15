"""trafilatura 正文提取：从渲染后的 HTML 抽取正文并按 maxChars 截断。"""


def extract_content(html: str, url: str, max_chars: int = 30000) -> tuple[str, bool]:
    """返回 (正文, 是否被截断)。提取失败时正文为空串。"""
    import trafilatura

    text = trafilatura.extract(html, url=url, favor_recall=True) or ""
    text = text.strip()
    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "..."
        truncated = True
    return text, truncated
