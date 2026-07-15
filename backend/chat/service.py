import asyncio
import json

from pydantic import BaseModel, Field

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

from backend.chat.runtime import fast_model, get_agent
from backend.chat.storage import ConversationStorage
from backend.chat.rag_context import get_last_rag_context
from backend.chat.streaming import set_rag_step_queue
from backend.chat.turn_context import reset_current_user_query, set_current_user_query
from backend.chat.web_context import reset_web_context
from backend.llm_utils import structured_invoke
from backend.tools import reset_knowledge_tool_calls, reset_web_tool_calls

storage = ConversationStorage()

CONTEXT_WINDOW_MESSAGES = 6


def _build_context_messages(
    messages: list,
    persistent_note: str,
    user_text: str,
    images: list[str] | None = None,
) -> list:
    short_term = messages[-CONTEXT_WINDOW_MESSAGES:] if len(messages) > CONTEXT_WINDOW_MESSAGES else messages
    context_messages: list = []
    if persistent_note:
        context_messages.append(
            SystemMessage(
                content=(
                    "【对话持久化笔记（你的工作记忆）】\n"
                    f"{persistent_note}\n"
                    "请参考以上笔记保持对话连贯性，避免重复回答已解决的问题。"
                )
            )
        )
    context_messages.extend(short_term)
    context_messages.append(HumanMessage(content=_build_human_content(user_text, images)))
    return context_messages


def _build_human_content(user_text: str, images: list[str] | None):
    """构造用户消息内容：有图片时用多模态 content block，否则用纯文本。"""
    if not images:
        return user_text
    content: list = [{"type": "text", "text": user_text}]
    for url in images:
        if not isinstance(url, str) or not url:
            continue
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content


def _is_final_agent_model_chunk(msg: AIMessageChunk, metadata: dict) -> bool:
    """只把顶层 agent 的最终回答流给前端，过滤工具内部的结构化模型调用。"""
    if getattr(msg, "tool_call_chunks", None):
        return False
    return metadata.get("langgraph_node") == "model"


async def update_persistent_note(
    current_note: str,
    user_text: str,
    ai_response: str,
) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: _update_persistent_note_sync(current_note, user_text, ai_response),
    )


def _generate_session_title_sync(user_text: str) -> str:
    try:
        prompt = (
            "请根据用户的首次提问，生成一个简短的对话标题（控制在 10 个字以内，不要标点）。\n"
            f"用户提问：{user_text}"
        )
        res = fast_model.invoke([HumanMessage(content=prompt)])
        title = (res.content or "").strip().strip('"').strip("。")
        return title or "新会话"
    except Exception as e:
        print(f"Title generation error: {e}")
        return "新会话"


async def generate_session_title(user_text: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _generate_session_title_sync(user_text))


def _update_persistent_note_sync(current_note: str, user_text: str, ai_response: str) -> str:
    try:
        prompt = (
            "你是一个【Context Manager Agent】(上下文管理器)，负责维护多轮对话中的「持久化笔记」。\n"
            "笔记是模型在有限上下文窗口下的长效工作记忆，记录已解决的问题与关键事实。\n\n"
            "更新规则：\n"
            "1. 将新信息与现有笔记智能合并，不要简单拼接。\n"
            "2. 过滤噪音，控制在 500 字以内，用简明条目输出。\n"
            "3. 若信息冲突，保留最可靠或最新版本。\n\n"
            f"▼ 现有笔记：\n{current_note if current_note else '无'}\n\n"
            f"▼ 最新一轮对话：\n用户：{user_text}\nAI：{ai_response}\n\n"
            "请直接输出更新后的笔记（纯文本，不要解释或 Markdown 代码块）："
        )
        res = fast_model.invoke([HumanMessage(content=prompt)])
        return (res.content or "").strip()
    except Exception as e:
        print(f"Context Manager Error: {e}")
        return current_note


class _ExtractedTodos(BaseModel):
    todos: list[str] = Field(default_factory=list, description="提取到的待办事项文本列表，无可执行任务时为空")


def _extract_todos_sync(user_text: str, ai_response: str) -> list[str]:
    try:
        prompt = (
            "你是一个待办事项提取器。从下面这轮对话中提取用户需要去做的、明确可执行的行动项（todo）。\n"
 "只提取用户需要亲自执行的具体任务（如：预约、提交、购买、联系某人、整理某物等），"
            "不要提取信息性问题、纯知识点、或已完成的事项。\n"
            "每个待办用简洁的中文祈使句表达，15 字以内。\n"
            "如果没有可提取的待办，返回空列表。\n\n"
            f"用户：{user_text}\nAI：{ai_response}"
        )
        res = structured_invoke(
            fast_model, _ExtractedTodos, [HumanMessage(content=prompt)]
        )
        return [t.strip() for t in (res.todos or []) if t.strip()]
    except Exception as e:
        print(f"Todo extraction error: {e}")
        return []


async def extract_todos(user_text: str, ai_response: str) -> list[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract_todos_sync(user_text, ai_response))


def _merge_todos(existing: list[dict], new_texts: list[str]) -> list[dict]:
    """将新提取的待办合并进已有列表：去重后追加，保留已有项的 done 状态。"""
    merged = [dict(t) for t in existing]
    existing_texts = {(t.get("text") or "").strip() for t in merged}
    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat()
    import uuid as _uuid
    for text in new_texts:
        if text and text not in existing_texts:
            merged.append({"id": _uuid.uuid4().hex, "text": text, "done": False, "created_at": now})
            existing_texts.add(text)
    return merged


def chat_with_agent(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
    images: list[str] | None = None,
    web_search_enabled: bool = False,
):
    messages, metadata = storage.load_with_meta(user_id, session_id)
    persistent_note = metadata.get("persistent_note", "")
    is_first_message = len(messages) == 0

    get_last_rag_context(clear=True)
    reset_knowledge_tool_calls()
    reset_web_tool_calls()
    reset_web_context()

    context_messages = _build_context_messages(messages, persistent_note, user_text, images)
    messages.append(HumanMessage(content=user_text))
    storage.save(user_id, session_id, messages)

    active_agent = get_agent(web_search_enabled)
    query_token = set_current_user_query(user_text)
    try:
        result = active_agent.invoke(
            {"messages": context_messages},
            config={
                "recursion_limit": 12,
                "run_name": "chat_with_agent",
                "tags": ["supermew", "chat", "non_stream"],
                "metadata": {
                    "user_id": user_id,
                    "session_id": session_id,
                    "web_search_enabled": web_search_enabled,
                    "has_images": bool(images),
                    "message_count": len(messages),
                },
            },
        )
    finally:
        reset_current_user_query(query_token)

    response_content = ""
    if isinstance(result, dict):
        if "output" in result:
            response_content = result["output"]
        elif "messages" in result and result["messages"]:
            msg = result["messages"][-1]
            response_content = getattr(msg, "content", str(msg))
        else:
            response_content = str(result)
    elif hasattr(result, "content"):
        response_content = result.content
    else:
        response_content = str(result)

    messages.append(AIMessage(content=response_content))

    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None

    save_meta = dict(metadata)
    if is_first_message:
        save_meta["title"] = _generate_session_title_sync(user_text)
    save_meta["persistent_note"] = _update_persistent_note_sync(
        persistent_note, user_text, response_content
    )

    try:
        existing_todos = save_meta.get("todos", []) or metadata.get("todos", [])
        new_todos = _extract_todos_sync(user_text, response_content)
        if new_todos:
            save_meta["todos"] = _merge_todos(existing_todos, new_todos)
    except Exception as e:
        print(f"Todo merge error: {e}")

    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(
        user_id,
        session_id,
        messages,
        metadata=save_meta,
        extra_message_data=extra_message_data,
    )

    return {
        "response": response_content,
        "rag_trace": rag_trace,
    }


async def chat_with_agent_stream(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
    images: list[str] | None = None,
    web_search_enabled: bool = False,
):
    messages, metadata = storage.load_with_meta(user_id, session_id)
    persistent_note = metadata.get("persistent_note", "")
    is_first_message = len(messages) == 0

    get_last_rag_context(clear=True)
    reset_knowledge_tool_calls()
    reset_web_tool_calls()
    reset_web_context()

    output_queue = asyncio.Queue()

    class _RagStepProxy:
        def put_nowait(self, step):
            output_queue.put_nowait({"type": "rag_step", "step": step})

    set_rag_step_queue(_RagStepProxy())

    context_messages = _build_context_messages(messages, persistent_note, user_text, images)
    messages.append(HumanMessage(content=user_text))
    storage.save(user_id, session_id, messages)

    title_task = None
    if is_first_message:

        def _on_title_done(fut):
            try:
                title = fut.result()
                output_queue.put_nowait(
                    {"type": "session_title", "title": title, "session_id": session_id}
                )
            except Exception as e:
                print(f"Title task error: {e}")

        title_task = asyncio.create_task(generate_session_title(user_text))
        title_task.add_done_callback(_on_title_done)

    full_response = ""

    async def _agent_worker():
        nonlocal full_response
        query_token = set_current_user_query(user_text)
        try:
            active_agent = get_agent(web_search_enabled)
            async for msg, _metadata in active_agent.astream(
                {"messages": context_messages},
                stream_mode="messages",
                config={
                    "recursion_limit": 12,
                    "run_name": "chat_with_agent_stream",
                    "tags": ["supermew", "chat", "stream"],
                    "metadata": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "web_search_enabled": web_search_enabled,
                        "has_images": bool(images),
                        "message_count": len(messages),
                    },
                },
            ):
                if not isinstance(msg, AIMessageChunk):
                    continue
                if not _is_final_agent_model_chunk(msg, _metadata):
                    continue

                content = ""
                if isinstance(msg.content, str):
                    content = msg.content
                elif isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, str):
                            content += block
                        elif isinstance(block, dict) and block.get("type") == "text":
                            content += block.get("text", "")

                if content:
                    full_response += content
                    await output_queue.put({"type": "content", "content": content})
        except Exception as e:
            await output_queue.put({"type": "error", "content": str(e)})
        finally:
            reset_current_user_query(query_token)
            await output_queue.put(None)

    agent_task = asyncio.create_task(_agent_worker())

    try:
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
    except GeneratorExit:
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        raise
    finally:
        set_rag_step_queue(None)
        if not agent_task.done():
            agent_task.cancel()

    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None

    if rag_trace:
        yield f"data: {json.dumps({'type': 'trace', 'rag_trace': rag_trace})}\n\n"

    yield "data: [DONE]\n\n"

    save_meta = dict(metadata)
    if is_first_message and title_task is not None:
        try:
            save_meta["title"] = await title_task
        except Exception:
            pass

    try:
        save_meta["persistent_note"] = await update_persistent_note(
            persistent_note, user_text, full_response
        )
    except Exception as e:
        print(f"Update persistent note error: {e}")

    try:
        existing_todos = save_meta.get("todos", []) or metadata.get("todos", [])
        new_todos = await extract_todos(user_text, full_response)
        if new_todos:
            save_meta["todos"] = _merge_todos(existing_todos, new_todos)
    except Exception as e:
        print(f"Todo merge error: {e}")

    messages.append(AIMessage(content=full_response))
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(
        user_id,
        session_id,
        messages,
        metadata=save_meta,
        extra_message_data=extra_message_data,
    )
