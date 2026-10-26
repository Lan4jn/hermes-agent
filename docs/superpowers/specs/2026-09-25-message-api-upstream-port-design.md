# Message API 上游移植规格

## 当前目标与最终目标

当前目标是在 `codex/upstream-port-20260925` 上，把 fork `main` 的 `/message` 契约移植到 `7b761da2de` 的 API Server 结构中，不引入旧版鉴权/网关大文件，不改变原有无密钥聊天机制。最终目标是按
[`docs/integration/2026-09-25/upstream-port-plan.md`](../../integration/2026-09-25/upstream-port-plan.md)
完成全部个性化功能的移植和交叉验收，再决定是否合入本地 `main`；本规格不授权推送、部署或修改正在运行的本地及 130 服务。

## 经确认的兼容边界

用户要求保留原机制，而不是把所有 `/message` 请求改成强制 Bearer 鉴权。以下行为必须逐项保持：

1. `message_api.enabled` 默认开启；关闭时 `/message` 和专属历史入口返回 404。`POST /message` 接受 `message`、`command`、`session_id`、`sender_id`、`sender_display_name`、`api_key`、`exec_token`。无 `session_id` 时回退到非空 `sender_id`；两者均未提供或均为空时，为**每次请求**生成不可预测的独立会话标识并在响应中返回，不再共用固定的 `remote` 会话。显式给出 `session_id`/`sender_id` 的旧客户端继续沿用原有续聊规则。会话与用户标记使用 `message_api:` 命名空间，不能混入普通 API Server 会话。自报 `sender_id` 不构成认证：知道某个值的人仍可能指定相同会话，隐私敏感调用应启用通话密钥并限制监听端口。
2. 通话密钥库中的 `require_chat_key` 状态默认关闭，**不写入 `config.yaml`**。关闭时，仅有 `message` 的无密钥请求仍进入原有完整 Agent、工具集和推理路径；开启时，聊天请求必须提供有效的专用通话密钥、管理员 Bearer `API_SERVER_KEY` 或原有有效 `message_api.api_keys`，否则返回 401 且不得调用模型。每个聊天请求从密钥库读取最新开关，跨进程修改立即生效，不需要重启 Gateway。成功时返回 `reply`、`session_id` 与 `command` 状态。**关闭开关不是只读或无工具沙盒**：能访问监听端口的客户端可能通过自然语言诱导 Agent 操作主机。这是明确保留的现有风险，而非将 `command` 字段鉴权误认为整个 Agent 的权限隔离。
3. 显式 `command` 只有在 `message_api.allow_command_execution=true` 且授权成立时执行；默认关闭。授权来源保留 Bearer `API_SERVER_KEY`、原有 `message_api.api_keys`（请求体或既有请求头）或尚未过期的 `exec_token`。有效原有执行密钥可签发有过期时间的执行令牌。**新建专用通话密钥永远不能授权显式命令，也不能签发执行令牌。** 未授权的纯命令返回 401；同一请求若还包含聊天消息，则聊天结果可返回，但命令不得执行。禁用命令执行时返回 403，不能因有效密钥越过开关。
4. `webui_history_enabled` 默认关闭。专属列表和详情入口仅在启用时可用，且始终要求 Bearer API Server 密钥；列表只显示 `message_api:` 标记的 API Server 会话，详情只返回该会话可见的 user/assistant 内容。`shared_memory_notes_enabled` 和 `session_history_delivery` 保持原来的默认关闭和会话行为。
5. 原 `main` **未提交**的 `agent_mode: "default" | "direct"` 及对应测试须在最终与用户工作区对账时保留：默认模式不变；`direct` 只允许单轮、无工具、跳过上下文文件/记忆/后台审查；无效值返回 400。不得在移植时直接改写原工作区的四个已修改文件。
6. `tools/hermes_message_tool.py` 的既有对等通信能力须有等价承载：按配置的 peer 或显式 base URL 调用对端 `/message`，保留会话、发送者、密钥/令牌字段和响应的大小/超时上限。先核对上游 `hermes peer dm` 能否满足同一调用契约；不能满足才移植最小的工具/CLI 能力，不能把 peer 的秘密塞进模型 schema 或日志。

## 架构与安全

API Server 已有 `_http_route_table()`、`_run_agent()`、profile-prefix middleware、并发准入和按 profile 隔离的 SessionDB。`/message` 应作为现有路由体系的一种入口，以独立的窄模块管理它的令牌、请求解析和历史投影；不要把数百行旧代码附加到 `gateway/platforms/api_server.py`。执行命令复用现有 terminal/approval 语义和 profile 作用域，不能自行启动无约束的 shell 子进程。专属历史入口从服务端会话标记过滤，不能相信客户端传入的 `sender_id` 即获得历史读取权限。

## 专用通话密钥管理

Dashboard 和 Desktop 分别提供 `/message` 通话密钥管理界面，共用**同一套后端密钥服务**，不各自保存一份密钥。管理员可以创建（必填名称）、查看名称/创建时间/短 ID、撤销；生成时一次性显示并支持复制明文，以后不得从管理 API 或 UI 重新读取。撤销立刻阻止后续聊天请求，不能影响已存在的旧式执行密钥或 `API_SERVER_KEY`。客户端优先通过 `X-Hermes-Message-Key` 请求头或 `chat_key` 请求体字段提交新密钥；为了兼容现有节点工具，也可以把新密钥放在原有 `api_key` 字段/请求头，但它只参与**聊天**授权，显式命令仍只核验第 3 条的原有凭据。仅有 `command`、没有 `message` 的请求不受 `require_chat_key` 影响。

后端按当前 profile 的 `get_hermes_home()` 存储：生成高熵随机明文，在专用私有 SQLite 状态库中仅保存不可逆摘要、随机记录 ID、名称、创建时间和一个 `require_chat_key` 布尔状态，以事务协调不同进程的更新并使用严格文件权限。**密钥和新开关都不进入** `config.yaml`、`.env`、浏览器持久状态、导出的配置或日志；现有 fork 和上游都没有该开关，故不做旧 YAML 迁移。备份/迁移此状态库时密钥与开关一起迁移，删除库会使开关恢复默认关闭并使旧通话密钥失效；数据库损坏/不可读时受保护的聊天必须失败关闭，不能把读取失败误判为“开关关闭”。普通客户端只能在 `/message` 使用密钥，不能调用创建/列表/撤销管理操作。

Dashboard 使用已有登录会话保护的新管理路由，不从浏览器直接请求 Gateway API Server；Desktop 使用现有已连接网关的 JSON-RPC 通道和契约生成机制，连接到远端时操作的是**所选远端 profile 的后端状态**，而非本机文件。两个适配器调用同一后端服务，并且沿用各自已有的管理身份检查；列表/撤销只作用于请求实际绑定的 profile，不允许客户端通过伪造 profile 参数读取另一 profile。界面沿用各自现有设置布局，提供中文和英文文案，失败时显示可重试错误，不重新显示明文。

`host: dual` 和 `allow_remote` 已在隔离分支的独立提交中恢复；它们只控制监听，**不替代 `/message` 的聊天鉴权**。部署时应只在可信网络或经防火墙限制的端口开放。既有 `message_api.enabled`、`allow_command_execution` 等原配置开关仍走 `config.yaml`；新 `require_chat_key` 只走专用 SQLite 状态库。密钥不应在测试、日志或规格中出现真实值。

## 失败与验收

- 无效 JSON/字段返回确定的 400；显式命令未授权返回上述 401/200 形态；配置禁用返回 403/404；异常对客户端保持受控错误，不泄露原始服务商凭据或主机敏感路径。
- 用 aiohttp `TestClient` 与真实路由注册测试默认关闭/开启 `require_chat_key`、无密钥聊天、管理员 Bearer、新通话密钥、原有执行密钥、过期执行令牌、禁用命令、聊天加未授权命令、显式会话复用、无身份字段的两个连续请求拿到不同 ID 且不共享历史、以及历史隔离；用真实导入和临时 `HERMES_HOME` 覆盖配置/SessionDB 路径。模型调用可在边界 mock，但不能用扫描源代码文本代替行为验证。
- 管理接口行为测试必须覆盖创建只回显一次、列表不含明文、撤销立即生效、同名/跨 profile 不串号、未登录拒绝、旧执行密钥不变、不同进程写开关后立即可见、无 `config.yaml` 写入及损坏状态库时拒绝放行；Dashboard 与 Desktop 各有创建/复制/撤销/失败提示的组件测试和类型检查。专用通话密钥即使填入原 `api_key` 字段，也不得让 `command.authorized` 变成 true。
- 按 `scripts/run_tests.sh` 运行相关 API Server、工具和会话测试；随后与本地工作区未提交 `agent_mode` 测试对账。审查者必须核对无密钥聊天仍可获得完整工具集，且文档明确风险。
- 其余 QQBot、Gemini、汉化、Windows/PM 子项目与最终构建、合并验收分别进行；本子项目通过不等于整体 GO。
