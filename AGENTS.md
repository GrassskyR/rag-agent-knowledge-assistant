# AGENTS.md

面向所有 AI 编码助手（Codex / Claude 等）的项目导航与协作约定。改代码前先读本文件。

> 行为准则源自 `.claude/CLAUDE.md`，UI 设计语言详见 `.claude/design-language.md`（注意：`.claude` 与 `.codex` 已在 `.gitignore` 中，仅本地可见）。本文件补充项目架构与工程约定。

---

## 0. 协作铁律

- **永远用中文回答与思考。**
- **先思考再编码**：明确假设；存在多种合理解释时先提出而非默认选择；有更简单的做法要直说并给出理由；不清楚就停下点名困惑点。
- **简单优先**：用解决问题的最少代码；不做未要求的扩展、抽象、配置项；不为不可能的场景写错误处理。问自己"资深工程师会不会觉得过度设计"。
- **外科手术式改动**：只动与请求直接相关的行；不顺手"改进"相邻代码、注释、格式；匹配现有风格；发现无关死代码只提示不删除；只清理自己改动产生的孤儿（未用 import 等）。每行改动都能追溯到用户请求。
- **目标驱动**：把任务转成可验证的成功标准（"加校验"→"写失败用例再让它过"），多步任务先给简短计划与每步的验证点，然后独立推进到验证通过。
- **项目语言**：永远用中文回答和提交，用 fix docs feat 等前缀 加上修改的内容提交 git

---

## 1. 项目概述

**生活助手（SuperMew）**：单用户/多会话的 AI 对话应用，核心是带 RAG 检索增强的 LangChain Agent。支持知识库文档上传、混合检索、多轮对话记忆、工具调用（知识库检索 / 天气查询），前端为极简单色聊天界面。

技术栈：

- 后端：Python 3.12+、FastAPI、LangChain + LangGraph、SQLAlchemy、Milvus（向量库）、PostgreSQL、Redis
- 前端：Vue 3（`<script setup>` + TS）、Pinia、Vite、纯 CSS（无 Tailwind / 组件库）、axios、marked + highlight.js、FontAwesome
- 部署：`docker compose` 起 Milvus 依赖（etcd / minio / standalone / attu）+ postgres + redis；后端静态托管编译后的 `frontend/dist`

---

## 2. 目录结构

```
SuperMew/
├── backend/
│   ├── app.py                # FastAPI 入口：create_app()，挂载静态资源、CORS、no-cache 中间件、startup init_db
│   ├── env.py                # 从项目根加载 .env（务必在 import 其它 backend 模块前调用一次）
│   ├── api/
│   │   ├── router.py         # 聚合 auth / sessions / chat / documents 四组路由
│   │   ├── resources.py      # 文档处理共享资源（loader / milvus / parent_store / 删除事务 / 上传目录）
│   │   └── routes/{auth,chat,documents,sessions}.py
│   ├── chat/
│   │   ├── runtime.py        # 模块级单例：agent / model / fast_model（create_agent + tools）
│   │   ├── service.py        # chat_with_agent / chat_with_agent_stream（核心对话编排）
│   │   ├── storage.py        # ConversationStorage：PG + Redis 缓存
│   │   ├── rag_context.py    # 单轮 RAG trace 暂存（工具→流式结束后落库）
│   │   └── streaming.py      # RAG 步骤 SSE 跨线程推送
│   ├── rag/
│   │   ├── pipeline.py       # LangGraph RAG 图：复杂度路由 / 检索 / 评分 / 重写 / 子 Agent 并行
│   │   └── utils.py          # 检索、step-back、HyDE、去重、rerank、trace 合并
│   ├── tools/                # @tool 工具：search_knowledge_base / get_current_weather
│   ├── indexing/             # 文档加载、三级分块、bge-m3 嵌入、Milvus 读写、父级分块存储
│   ├── jobs/upload_jobs.py   # 上传/删除异步任务进度管理（内存态，线程安全）
│   ├── schemas/              # Pydantic 请求/响应模型
│   ├── db/models.py          # SQLAlchemy 模型：User / ChatSession / ChatMessage / ParentChunk
│   └── infra/                # database / auth(JWT) / cache(Redis)
├── frontend/
│   ├── src/
│   │   ├── App.vue           # 根布局：Sidebar + MainContent（AuthPanel / DocumentSettings / ChatArea）
│   │   ├── main.ts           # createApp + Pinia，挂载全局 CSS / FontAwesome / highlight.js 主题
│   │   ├── components/       # Sidebar、AuthPanel、HistorySidebar、Chat/*、Documents/*
│   │   ├── stores/           # auth / chat / sessions / documents（Pinia）
│   │   ├── utils/{api,markdown}.ts
│   │   ├── types/            # chat / user / document 类型
│   │   └── assets/styles/main.css   # 全局样式 + :root 设计令牌（唯一样式来源）
│   └── vite.config.ts        # dev 代理 /auth /chat /sessions /documents → :8000
├── data/                     # 上传文档与 BM25 状态（gitignore）
├── docker-compose.yml        # Milvus 依赖 + postgres + redis
├── pyproject.toml            # uv 管理依赖
└── .env / .env.example
```

---

## 3. 后端架构

### 3.1 应用启动

`backend/app.py` 的 `create_app()`：注册 startup 钩子初始化数据库表（`init_db()`），开启全开放 CORS，加 `no-cache` 中间件（对 `/` 及 `.html/.js/.css` 禁缓存），挂载 `router`，最后把 `frontend/dist` 作为静态站点挂到 `/`。支持 `python backend/app.py` 与 `uvicorn backend.app:app` 两种启动。`backend/env.py` 的 `load_env()` 必须在导入其它 backend 模块前调用一次。

### 3.2 对话主流程

入口 `backend/api/routes/chat.py`：

- `POST /chat`：非流式，`chat_with_agent` 返回 `{response, rag_trace}`。
- `POST /chat/stream`：SSE 流式，`chat_with_agent_stream` 逐事件 yield。事件类型：`content`（增量文本）、`rag_step`（检索步骤实时进度）、`trace`（最终 RAG trace）、`session_title`（首条消息生成的会话标题）、`error`、`[DONE]`。

`backend/chat/service.py` 编排：

1. `storage.load_with_meta(user_id, session_id)` 取历史消息 + 会话元数据（`persistent_note` 持久化笔记、`title`）。
2. `_build_context_messages`：拼装系统笔记 + 最近 `CONTEXT_WINDOW_MESSAGES=6` 条 + 当前 HumanMessage。
3. 重置 RAG 上下文与工具调用计数；落库当前用户消息。
4. 流式：`agent.astream(..., stream_mode="messages")`，过滤 tool_call_chunks，逐块推送 `content`；标题生成与持久化笔记更新并行（`fast_model`）。
5. 流结束后取 `rag_trace` 推送，再落库 AI 消息（带 rag_trace）与更新后的元数据。

`backend/chat/runtime.py` 是模块级单例：`init_chat_model`（OpenAI 兼容协议，走 `BASE_URL`/`ARK_API_KEY`）+ `create_agent(model, tools, system_prompt)`。`fast_model` 用于标题与上下文管理。`SYSTEM_PROMPT` 约束：每轮最多一次知识库工具调用，拿到结果必须直接出最终答案并按 `[1]` 内联引用。

### 3.3 对话存储

`backend/chat/storage.py` 的 `ConversationStorage`：PostgreSQL 持久化（`ChatSession` / `ChatMessage`），Redis 做消息列表与会话列表缓存（键 `chat_messages:{user}:{session}`、`chat_sessions:{user}`，TTL 默认 300s）。会话元数据 JSON 存 `title` 与 `persistent_note`（Context Manager Agent 维护的长效工作记忆，≤500 字）。

### 3.4 RAG 检索图

`backend/rag/pipeline.py` 用 LangGraph 编排，`run_rag_graph(question)` 入口：

- `classify_complexity`（FAST_MODEL）→ 简单问题走标准路径，复杂问题走分解并行路径。
- **简单路径**：`retrieve_initial` →（无结果或评分不足）`rewrite_question`（策略 step_back / hyde / complex）→ `retrieve_expanded` → END；或评分通过直接 END。
- **复杂路径**：`decompose_question`（拆 2–4 子问题）→ `Send` 并行分发到 `rag_sub_agent` 子图（每个子问题独立跑完整检索）→ `synthesis` 合并去重 → END。
- 检索底层 `backend/rag/utils.py`：Milvus 混合检索（稠密 bge-m3 + 稀疏 BM25）、三级分块 + auto-merging、可选 rerank（未配置自动降级）、`RERANK_MIN_SCORE` 过滤。
- RAG trace 通过 `rag_context.record_rag_context` 暂存，检索步骤通过 `streaming.emit_rag_step` 跨线程安全推到 SSE 队列；子 Agent 用 `set_sub_agent_group` 标识分组。

### 3.5 工具

`backend/tools/`：

- `search_knowledge_base`（`@tool`）：每轮限调 1 次（`reset_knowledge_tool_calls` 在对话开始重置），调用 `run_rag_graph`，记录 rag_context，按 `[i] source (Page n)` 格式返回。
- `get_current_weather`：高德天气 API，支持 `base`/`all`。

### 3.6 文档索引

`backend/indexing/`：

- `DocumentLoader`：PDF/Word/Excel/HTML 解析 + 三级分块（chunk_size=800, overlap=100）。L1/L2 父级分块入 PostgreSQL `ParentChunk` + Redis；L3 叶子分块入 Milvus。
- `EmbeddingService`：`langchain_huggingface` + BAAI/bge-m3（稠密 1024 维，`HF_ENDPOINT` 走国内镜像）。
- `MilvusStore`：集合管理、插入、混合/稠密检索、删除；`get_milvus_store()` 单例。
- `MilvusWriter`：批量向量化入库，带 `progress_callback`。
- `ParentChunkStore`：父级分块 CRUD + Redis 缓存，供 auto-merging 回溯父级。

### 3.7 文档管理接口

`backend/api/routes/documents.py`（**仅 admin**）：同步上传/删除与异步 job 版本（`/documents/upload/async`、`/documents/delete/async/{filename}`）。异步 job 由 `UploadJobManager`（`backend/jobs/upload_jobs.py`，内存态、线程安全）管理多步骤进度。删除走 `delete_document_transactionally`：先删 Milvus 向量，再删 PG 父级分块与 Redis 缓存（Milvus 2.5+ BM25 统计服务端自动维护）。支持格式：`.pdf .docx .doc .xlsx .xls .html .htm`。

### 3.8 认证与基础设施

- `backend/infra/auth.py`：JWT（HS256，默认 1440 分钟），`OAuth2PasswordBearer(tokenUrl="/auth/login")`。密码用 `pbkdf2_sha256`（兼容旧 passlib/bcrypt）。`require_admin` 守卫文档接口；`resolve_role` 凭 `ADMIN_INVITE_CODE` 升级 admin。
- `backend/infra/database.py`：SQLAlchemy 引擎，全局 `before_cursor_execute` 监听器递归清洗 NUL / 零宽 / 不可见 / PUA 字符并 NFC 规范化，避免 PG 写入异常。`init_db()` 建表。
- `backend/infra/cache.py`：`RedisCache`，键前缀 `supermew`，`get_json/set_json/delete`。

---

## 4. 前端架构

- 入口 `main.ts`：`createApp` + Pinia，挂载 `main.css`、FontAwesome、highlight.js 主题。
- `App.vue`：未登录显 `AuthPanel`；登录后按 `chatStore.activeNav` 切 `DocumentSettings` / `ChatArea`，`HistorySidebar` 侧滑。
- 状态：`stores/auth`（token、`fetchMe`、登出）、`stores/chat`（消息列表、`handleSend` 走 SSE、RAG 步骤分组 `appendRagStepToGroups`、终止 `AbortController`）、`stores/sessions`、`stores/documents`。
- 聊天流：`ChatInput` → `chatStore.handleSend` → `fetch('/chat/stream', {stream})` 手动解析 SSE（按 `\n\n` 切事件，`data: ` 前缀 JSON），逐事件更新消息。`/chat`、`/auth`、`/sessions`、`/documents` 走 `utils/api.ts`（axios，拦截器注入 Bearer、401 触发 `unauthorized` 事件登出）。
- 组件：`Chat/ChatArea`、`ChatInput`、`MessageItem`、`MessageContent`（marked 渲染）、`References`、`RetrievalTraceDetails`、`ThinkingTrace`、`WelcomeScreen`；`Documents/UploadSection`、`DocumentItem`、`DocumentSettings`。
- Vite dev server 跑在 3000，代理后端接口到 8000；生产由后端静态托管 `dist`。

---

## 5. 开发与运行命令

```bash
# 后端依赖（推荐 uv）
uv sync
uv run uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
# 或 uv run python backend/app.py

# 基础设施（Milvus + PG + Redis）
docker compose up -d
docker compose ps

# 前端
cd frontend
npm install
npm run build      # 产物进 frontend/dist，后端启动自动托管
npm run dev        # dev server :3000，代理后端到 :8000
```

环境变量从 `.env` 读取（复制 `.env.example`）：模型（`ARK_API_KEY` / `MODEL` / `GRADE_MODEL` / `FAST_MODEL` / `BASE_URL`）、嵌入（`EMBEDDING_MODEL` / `EMBEDDING_DEVICE` / `DENSE_EMBEDDING_DIM` / `HF_ENDPOINT`）、rerank（可选）、检索候选与 auto-merge、Milvus、`DATABASE_URL`、`REDIS_URL`、JWT、`AMAP_*`。

端口：PG 5432、Redis 6379、Milvus 19530（健康检查 9091）、MinIO 9000/9001、Attu 8080、后端 8000、前端 dev 3000。

---

## 6. UI 设计语言（要点）

改任何 UI 前先读 `.claude/design-language.md`。核心约束：

- Vue 3 `<script setup>` + **纯 CSS**，**禁止引入 Tailwind / UnoCSS / 任何组件库**。所有样式集中进 `frontend/src/assets/styles/main.css`，由 `:root` 设计令牌驱动；不写组件内 scoped `<style>`。
- 单色黑/白/灰，**黑色 `--accent` 是唯一强调色**（主按钮、发送、链接、引用角标）；不引入彩色，语义色仅 `--danger`/`--success` 且弱化使用。
- 优先复用已有 CSS 变量，**不硬编码 `#xxx`**；确需新值再加到 `:root`。
- 边框近隐形（`--border-color` = gray-100），大量留白，克制动效（0.15s）。AI 回答是纯文本无气泡无底色；用户气泡用 `--user-msg-bg`。
- 圆角体系：按钮/输入 `--radius-sm`(8px)、列表 `--radius-md`(12px)、用户气泡 `--radius-lg`(16px)、输入框药丸 `--radius-xl`(24px)、chips/圆形 `--radius-pill`。
- 图标统一 FontAwesome solid（`fas`），默认灰。输入区是浮动药丸，内含 textarea + action chips + 黑色圆形发送按钮。

---

## 7. 工程约定

- 包管理用 `uv`（`pyproject.toml` + `uv.lock`）；前端用 npm。不要混入其它包管理器。
- 新增后端依赖必须进 `pyproject.toml` 并 `uv sync`；新增前端依赖必须进 `frontend/package.json`。
- 数据库模型改动后，`init_db()` 只 `create_all` 不做迁移——开发期可直接建表；如引入 Alembic 需另行约定。
- Milvus 集合与 BM25 索引由 `MilvusStore.ensure_collection` 管理；删除向量后 BM25 统计由 Milvus 2.5+ 服务端自动维护，无需手动同步。
- Redis 缓存键前缀统一 `supermew`；写库后记得 `cache.delete` 对应会话/列表键。
- 前端 SSE 用原生 `fetch` 手动解析（非 EventSource，以便带 Authorization 头与 abort）。
- 任何写入 PG 的字符串都会被全局监听器清洗不可见字符——业务层无需手动 `replace`，但不要依赖原始字节完整性。
- 遵循 `.gitignore`：`.env`、`data/`、`volumes/`、`node_modules/`、`frontend/dist/`、`.claude`、`.codex` 均不入库。
