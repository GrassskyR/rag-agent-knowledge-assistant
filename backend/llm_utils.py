"""LLM 结构化输出的供应商兼容封装。

`ChatOpenAI.with_structured_output` 默认走 function-calling，对「OpenAI 协议兼容
但 function-calling 不完整」的端点会抛错。`structured_invoke` 先尝试原生路径，
失败时回退到「提示输出 JSON + 文本解析」，与项目内 grader 节点的解析思路一致。
"""
import json
import re
from typing import Any, Type

from pydantic import BaseModel

_FENCED_JSON = re.compile(r"```(?:json)?\s*(.*?)```", flags=re.DOTALL | re.IGNORECASE)


def _message_content_to_text(content: Any) -> str:
    """把模型返回的 content（str 或 list[str|dict]）统一成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text = ""
        for block in content:
            if isinstance(block, str):
                text += block
            elif isinstance(block, dict):
                text += block.get("text") or block.get("content") or ""
        return text
    return str(content or "")


def _extract_first_json(text: str) -> Any:
    """从文本中抽取首个 JSON 对象/数组：先剥离 ```json 围栏，再用 raw_decode 容错解析。"""
    text = (text or "").strip()
    fenced = _FENCED_JSON.search(text)
    if fenced:
        text = fenced.group(1).strip()

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[idx:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def structured_invoke(model: Any, schema: Type[BaseModel], messages: list) -> BaseModel:
    """以 schema 约束调用 model；原生 function-calling 失败则回退到提示+解析。

    回退解析仍失败时抛异常，交由调用点既有的 try/except 兜底默认值处理。
    """
    try:
        return model.with_structured_output(schema).invoke(messages)
    except Exception:
        pass

    json_schema = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    instruction = (
        "请严格输出符合如下 JSON Schema 的 JSON 对象，"
        "只输出 JSON 本身，不要任何解释、不要 markdown 代码块：\n"
        f"{json_schema}"
    )
    fallback_messages = list(messages) + [{"role": "user", "content": instruction}]
    resp = model.invoke(fallback_messages)
    text = _message_content_to_text(getattr(resp, "content", resp))
    obj = _extract_first_json(text)
    if obj is None:
        raise ValueError(f"structured_invoke 回退解析失败: {text[:200]!r}")
    return schema.model_validate(obj)
