# 文档替换与会话持久化缺陷修复

日期：2026-09-17。

本次修复两类数据问题：同名文档替换失败时破坏旧文件或旧索引，以及新增聊天消息时删除重建全部历史。保留现有 HTTP/SSE 数据格式和数据库表结构，未新增依赖。

## 1. 文档替换与删除

### 缺陷与原因

原同步上传先删除同名文件和索引，再保存、解析新文件；原异步上传先覆盖正式文件，再删除旧索引、解析新文件。两条路径都在确认新文档可用之前破坏旧版本。

因此，同名 PDF 无法解析时，任务虽然显示失败，旧内容已经不可检索。父块写入成功、后续向量批次失败时，还会留下部分新数据。原 `delete_document_transactionally()` 只有跨存储的顺序调用，没有事务回滚能力。

另外，父块缓存在 PostgreSQL 提交前更新，提交失败时可能向读取者暴露未提交内容。同名文档的新旧分块 ID 由文件名、页码与位置生成，会发生重合，不能直接把“写新索引”和“删除旧索引”交换顺序解决问题。

### 修复流程

同步上传、单文件异步上传和批量异步上传共用 [resources.py](../backend/api/resources.py) 中的替换逻辑：

1. 上传内容保存到 `data/documents/.staging/` 中的唯一临时文件，保留原扩展名。保存失败或取消时清理该临时文件。
2. 解析新文档并校验内容及叶子分块。此阶段失败，旧正式文件和旧索引保持不变。
3. 获取进程内文档写锁，读取当前文件的完整父块和叶子向量快照。快照失败时不开始删除。
4. 删除旧索引，写入新父块和新叶子向量。新分块的 `file_path` 指向正式文件路径，不能保留临时路径。
5. 所有索引写入成功后，用同文件系统的 `os.replace()` 发布正式文件。这是本次替换的成功提交点。
6. 索引修改或文件发布失败时，清理当前文件的索引，再从快照恢复旧父块和叶子向量。首次上传的快照为空，补偿后应无残留索引。
7. 任务进度跟随处理阶段更新。进度回调异常只记录日志，不能撤销已经发布的文档。

快照直接从 PostgreSQL 读取父块，绕过缓存；Milvus 使用强一致查询迭代器完整读取，避免 offset 查询窗口限制。恢复时复用旧密集向量，仅写回业务字段，排除查询附带的自动主键；BM25 稀疏向量由 Milvus 重新生成。

删除与替换共用同一写锁。删除按“Milvus → PostgreSQL/缓存 → 本地文件”推进，已不存在的数据允许重复删除，中途失败可重新发起删除以完成剩余步骤。同步上传与删除通过线程池执行阻塞流程。

### 函数与数据契约

| 函数 | 契约 |
| --- | --- |
| `async stage_upload_file(file: UploadFile, filename: str) -> Path` | 校验路径并返回已保存的临时文件；不修改正式文件 |
| `replace_document(filename: str, staged_path: Path, *, on_progress: Callable[[DocumentProgress], None] \| None = None) -> ReplacementResult` | 管理解析、快照、写入、发布、补偿与临时文件清理；完整成功才返回 |
| `delete_document(filename: str, *, on_progress: Callable[[DocumentProgress], None] \| None = None) -> int` | 顺序删除索引与文件，返回本次实际删除的向量条数 |
| `ParentChunkStore.get_documents_by_filename(self, filename: str) -> list[dict]` | 从数据库读取该文件的完整父块快照 |

`ReplacementResult` 包含 `filename`、`parent_count` 和 `leaf_count`。`DocumentIndexSnapshot` 包含 `parents` 和 `leaf_rows`，只保存当前被替换文件的数据。

`DocumentProgress` 包含 `step`、`status`、`percent`、`message`，向量阶段可携带 `processed_chunks`、`total_chunks`。上传步骤按 `upload → parse → cleanup → parent_store → vector_store` 展示，文件发布前最后一步最多显示 99%。

`DocumentOperationError` 保留原始异常链，并提供 `step`、`recovery`、`recovery_error`：

| recovery | 含义 |
| --- | --- |
| `unchanged` | 尚未修改原文档及索引 |
| `restored` | 替换失败，已经恢复替换前的索引 |
| `incomplete` | 补偿失败；错误文本同时说明原始失败与恢复失败 |
| `retry_delete` | 删除未完成，可以重新发起删除 |

路由将这些结果映射为既有 HTTP 错误或任务的 `error/message`，不新增响应字段。父块写入调整为数据库提交成功后失效缓存。Milvus 文件名条件使用 JSON 字符串转义。

### 保证范围

这是当前单进程部署中的运行时失败补偿，不是跨 PostgreSQL、Milvus 和文件系统的原子事务。检索读取没有获取文档写锁，替换期间可能看到中间状态。快照只存在内存，进程崩溃或补偿持续失败时不提供自动恢复。

恢复保证旧内容、分块关联和密集向量；Milvus 自动 ID 可能改变，父块更新时间会重新生成。当前快照会占用与该文档父块及密集向量数量相应的内存。

## 2. 会话增量持久化

### 缺陷与原因

原 `ConversationStorage.save()` 要求调用者传入完整历史，每次先删除该会话全部消息，再逐条插入，并给所有记录赋同一个当前时间。

正常一轮聊天分别在用户消息与 AI 消息产生后保存一次。已有 n 条历史时，一轮插入 `2n+3` 行，而实际新增仅两条；例如已有 200 条历史时插入 403 行。历史消息 ID、时间戳也会随新消息不断改变。

### 修复方案与契约

用以下方法替代全量 `save()`：

`append_message(self, user_id: str, session_id: str, message: BaseMessage, *, metadata: dict | None = None) -> None`

- `user_id` 延续现有语义，对应用户名；用户不存在时继续跳过持久化，兼容评估入口。
- 每次只新增一条 `ChatMessage`，保留全部旧消息的 ID、时间、正文和 trace。
- `rag_trace` 从当前消息的 `additional_kwargs` 读取，移除 `extra_message_data` 的历史列表下标协议。
- 可选 `metadata` 按原规则浅合并，与当前消息在同一事务提交；更新会话的 `updated_at`。
- 提交成功后失效消息列表与会话列表缓存，由现有读取路径重建。缓存继续使用既有尽力而为策略。
- 不按正文去重，不自动重试追加。相同正文可能是合法追问；同会话串行仍由现有会话锁负责。

[service.py](../backend/chat/service.py) 中五处保存调用均已迁移：同步用户消息、同步 AI 消息、流式用户消息、流式完成回答、流式终止回答。

流式消息提交成功后才发送 `response_complete`；标题和持久化笔记保存后才发送 `[DONE]`。`response_saved` 仍用于避免正文已经保存后，终止分支重复写入 AI 消息。

历史读取、模型上下文窗口、历史图片存储策略和两种聊天入口的错误处理保持原样。修复仅阻止后续重写，无法还原此前已经丢失的历史时间戳。

## 3. 涉及文件

| 文件 | 修改内容 |
| --- | --- |
| [backend/api/resources.py](../backend/api/resources.py) | 文档暂存、替换、快照、补偿、删除与进度契约 |
| [backend/api/routes/documents.py](../backend/api/routes/documents.py) | 上传入口共用替换流程，任务进度适配，阻塞操作转线程池 |
| [backend/indexing/milvus_client.py](../backend/indexing/milvus_client.py) | 完整快照改用强一致查询迭代器 |
| [backend/indexing/parent_chunk_store.py](../backend/indexing/parent_chunk_store.py) | 父块快照读取与提交后缓存失效 |
| [backend/jobs/upload_jobs.py](../backend/jobs/upload_jobs.py) | 先解析、再清理旧版本的进度顺序 |
| [backend/chat/storage.py](../backend/chat/storage.py) | 单消息增量写入 |
| [backend/chat/service.py](../backend/chat/service.py) | 迁移五处保存调用与 trace 传递 |
| [test_document_uploads.py](../test_document_uploads.py) | 保留已有七项上传行为测试，适配依赖归属 |
| [test_document_lifecycle.py](../test_document_lifecycle.py) | 新增七项文档失败测试 |

## 4. 验证结果

### 自动化检查

运行 `uv run --no-sync python -m unittest test_document_uploads test_document_lifecycle -q`，14 项测试通过。仅新增七项文档失败测试，没有新增会话或其他测试。

新增覆盖：三种上传入口解析失败、暂存失败、快照失败、向量部分写入失败（替换和首次上传）、文件发布失败、补偿失败、删除途中失败后的重试。相关 Python 文件语法检查及 `git diff --check` 通过，前端 `npm run build` 成功。

### 真实端到端验证

2026-09-17 使用本地 Playwright/Chromium、真实 FastAPI、PostgreSQL、Redis、Milvus、本地 bge-m3 和配置中的聊天模型完成以下九项检查：

| 场景 | 结果 |
| --- | --- |
| 浏览器注册管理员并登录 | 成功 |
| 浏览器上传 PDF | 写入 2 个父块、1 个叶子向量，正式文件可读取 |
| 浏览器上传损坏的同名 PDF | 解析失败，旧文件字节、父块和向量保持不变 |
| 浏览器正常替换同名 PDF | 文件和索引更新为新内容，不含暂存路径 |
| 首次上传时文件发布失败 | 在独立验证路径放置目录，触发真实 `os.replace()` 失败；已写入父块和向量清零 |
| 替换已有文档时文件发布失败 | 暂存验证文件并在其正式路径制造目录冲突，旧索引保持可用于快照；失败后旧文本、父块和密集向量恢复，随后还原验证文件 |
| 浏览器两轮真实模型对话 | 消息 ID 从 `[167, 168]` 增加到 `[167, 168, 169, 170]`，旧消息 ID、时间、正文、trace 均不变 |
| 会话历史查询及流式完成 | 返回的 4 条消息与数据库内容及顺序一致；第二轮 SSE 观察到 `response_complete` 和 `[DONE]` |
| 浏览器删除文档 | 父块和向量清零，文件读取返回 404 |

浏览器未捕获到页面脚本异常。验证账号、会话、文档、索引、缓存和临时凭据已清理，后端重启清除本次内存任务记录。

验证时宿主机 5432 端口冲突，PostgreSQL 临时映射到 `127.0.0.1:15432`，保留原数据卷；后端仅通过进程环境覆盖数据库端口。项目 `.env` 和 `docker-compose.yml` 未修改，此端口调整不属于代码修复。
