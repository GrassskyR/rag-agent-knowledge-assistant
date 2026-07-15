import os

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model

from backend.tools import (
    get_current_weather,
    search_knowledge_base,
    web_fetch,
    web_search,
)

API_KEY = os.getenv("ARK_API_KEY")
MODEL = os.getenv("MODEL")
FAST_MODEL = os.getenv("FAST_MODEL") or MODEL
BASE_URL = os.getenv("BASE_URL")

SYSTEM_PROMPT = (
    "You are a helpful life assistant for everyday tasks. "
    "When responding, you may use tools to assist. "
    "Use search_knowledge_base when users ask document/knowledge questions. "
    "Do not call the same tool repeatedly in one turn. At most one knowledge tool call per turn. "
    "Once you call search_knowledge_base and receive its result, you MUST immediately produce the Final Answer based on that result. "
    "After receiving search_knowledge_base result, you MUST NOT call any tool again (including get_current_weather or search_knowledge_base). "
    "If the retrieved context is insufficient, answer honestly that you don't know instead of making up facts. "
    "When answering based on retrieved chunks, you MUST cite the source chunks using their index numbers inline, for example [1] or [2][3]. "
    "If tool results include a Step-back Question/Answer, use that general principle to reason and answer, "
    "but do not reveal chain-of-thought. "
    "If you don't know the answer, admit it honestly."
)

WEB_SEARCH_SYSTEM_PROMPT = (
    "You are a helpful life assistant for everyday tasks. "
    "You have four tools: get_current_weather, search_knowledge_base, web_search, web_fetch.\n\n"
    "Routing guidance (soft, use your judgment):\n"
    "- For document/knowledge questions, prefer search_knowledge_base first.\n"
    "- For real-time / external / current information (latest versions, news, public facts beyond your knowledge), "
    "use web_search to get numbered results (title + snippet + url), then decide which links are worth opening, "
    "and call web_fetch with 1-3 of the most valuable urls to read concise summaries focused on the question.\n\n"
    "Workflow for web questions: web_search → judge → web_fetch(urls) → answer. "
    "You may call web_search at most twice and web_fetch at most three times per turn "
    "(cumulative urls are capped). Once you have enough information, produce the Final Answer; "
    "do not keep calling tools unnecessarily.\n\n"
    "When answering from web sources or retrieved chunks, you MUST cite the source numbers inline, "
    "for example [1] or [2][3]. The numbers must match the [n] numbers returned by web_search / web_fetch. "
    "If tool results include a Step-back Question/Answer, use that general principle to reason and answer, "
    "but do not reveal chain-of-thought. "
    "If you don't know the answer, admit it honestly."
)

_agents = {}


def create_agent_instance():
    model = init_chat_model(
        model=MODEL,
        model_provider="openai",
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.3,
        stream_usage=True,
    )

    fast_model = init_chat_model(
        model=FAST_MODEL,
        model_provider="openai",
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.2,
        stream_usage=True,
    )

    return model, fast_model


model, fast_model = create_agent_instance()


def get_agent(web_search_enabled: bool = False):
    key = "web" if web_search_enabled else "default"
    if key not in _agents:
        if web_search_enabled:
            tools = [get_current_weather, search_knowledge_base, web_search, web_fetch]
            system_prompt = WEB_SEARCH_SYSTEM_PROMPT
        else:
            tools = [get_current_weather, search_knowledge_base]
            system_prompt = SYSTEM_PROMPT
        _agents[key] = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )
    return _agents[key]
