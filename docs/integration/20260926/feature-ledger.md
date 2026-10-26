# 115 个变更文件双向功能台账 (Feature Ledger - Verified)

> **审计核准日期**：2026-09-26
> **审计基准**：基于工作树物理文件扫描与全链路真实测试结果校验。
> **状态分类标准**：
> - **原路径保留**：文件在原路径保留，个性化功能与契约完好，附带真实测试；
> - **迁移且有等价证据**：功能或代码重构迁移至新路径，有明确的真实目标入口与真实测试证明等价；
> - **已删除且无保全要求**：历史临时草案、已废弃旧实现或已重组文件，上游与本架构均无保全要求；
> - **待验证**：尚未获得充分自动化测试证据（当前台账为 0 项）。

| 序号 | 原文件路径 (origin/main) | 当前目标路径 | 状态类别 | 真实行为与回归测试证据 | 说明与处置决策 |
| :--- | :--- | :--- | :---: | :--- | :--- |
| 1 | `.agents/skills/superpowers-debugging/SKILL.md` | 无 | 已删除且无保全要求 | 外部开发辅助技能，非生产运行资产 | 历史开发会话引入，删除不影响运行时 |
| 2 | `.agents/skills/superpowers-review/SKILL.md` | 无 | 已删除且无保全要求 | 外部开发辅助技能，非生产运行资产 | 历史开发会话引入，删除不影响运行时 |
| 3 | `.agents/skills/superpowers-tdd/SKILL.md` | 无 | 已删除且无保全要求 | 外部开发辅助技能，非生产运行资产 | 历史开发会话引入，删除不影响运行时 |
| 4 | `.agents/skills/superpowers/SKILL.md` | 无 | 已删除且无保全要求 | 外部开发辅助技能，非生产运行资产 | 历史开发会话引入，删除不影响运行时 |
| 5 | `.gitignore` | `.gitignore` | 原路径保留 | `git status` 规则校验 | 忽略 node_messages、构建临时产物与缓存 |
| 6 | `agent/agent_runtime_helpers.py` | `agent/agent_runtime_helpers.py` | 原路径保留 | `tests/agent/test_gemini_cloudcode.py` | 挂载 google-gemini-cli client 与 proxy 支持 |
| 7 | `agent/auxiliary_client.py` | `agent/auxiliary_client.py` | 原路径保留 | `tests/agent/test_gemini_endpoints.py` | 支持 gemini cli client 辅助调用 |
| 8 | `agent/credential_pool.py` | `agent/credential_pool.py` | 原路径保留 | `tests/agent/test_credential_pool.py` | gemini custom oauth token 池及刷新支持 |
| 9 | `agent/gemini_cloudcode_adapter.py` | `agent/gemini_cloudcode_adapter.py` | 原路径保留 | `tests/agent/test_gemini_cloudcode.py` (199✓) | CloudCode / Code Assist 协议适配器 |
| 10 | `agent/gemini_endpoints.py` | `agent/gemini_endpoints.py` | 原路径保留 | `tests/agent/test_gemini_endpoints.py` (90✓) | gemini endpoints proxy 与路由解析 |
| 11 | `agent/gemini_native_adapter.py` | `agent/gemini_native_adapter.py` | 原路径保留 | `tests/agent/test_gemini_endpoints.py` | 自定义 base_url 与 proxy 支持 |
| 12 | `agent/google_code_assist.py` | `agent/google_code_assist.py` | 原路径保留 | `tests/agent/test_gemini_cloudcode.py` | Google Code Assist API 客户端通信实现 |
| 13 | `agent/google_oauth.py` | `agent/google_oauth.py` | 原路径保留 | `tests/agent/test_google_oauth.py` | Google OAuth PKCE 与 token 刷新机制 |
| 14 | `agent/prompt_builder.py` | `agent/prompt_builder.py` | 迁移且有等价证据 | `tests/agent/test_prompt_builder.py` | 上游重构提示词装配器，字节级前缀缓存完全一致 |
| 15 | `agent/system_prompt.py` | `agent/system_prompt.py` | 原路径保留 | `tests/agent/test_system_prompt.py` | 包含跨节点说明且不破坏前缀缓存 |
| 16 | `agent/transports/chat_completions.py` | `agent/transports/chat_completions.py` | 迁移且有等价证据 | `tests/agent/test_chat_completions.py` | 传输层已与上游现代流式实现完全融合 |
| 17 | `cli.py` | `cli.py` | 原路径保留 | `tests/hermes_cli/test_gquota_command.py` | 挂载 `/gquota` 配额查询等定制 CLI 指令 |
| 18 | `docs/integration/2026-09-14/code-differences.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 由 `docs/integration/20260926/baseline.md` 替代 |
| 19 | `docs/integration/2026-09-14/development-plan.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 由 `docs/integration/20260926/baseline.md` 替代 |
| 20 | `docs/integration/2026-09-14/spec.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 由 `docs/integration/20260926/compatibility-spec.md` 替代 |
| 21 | `docs/integration/2026-09-14/zcode-next-task.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 临时任务记录，已废弃 |
| 22 | `docs/integration/2026-09-16/compatibility-completion-spec.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 由 `docs/integration/20260926/compatibility-spec.md` 替代 |
| 23 | `docs/integration/2026-09-16/upstream-integration-completion-plan.md` | 无 | 已删除且无保全要求 | 历史过程草案 | 由最新执行计划替代 |
| 24 | `docs/superpowers/plans/2026-08-22-google-gemini-cli-custom-endpoints.md` | 无 | 已删除且无保全要求 | 历史设计方案 | 对应实现已入库并经测试验证，方案无单独保全要求 |
| 25 | `docs/superpowers/specs/2026-07-22-hermes-manager-design.md` | 无 | 已删除且无保全要求 | 历史设计方案 | 已由现代 PM 架构取代 |
| 26 | `docs/superpowers/specs/2026-08-22-google-gemini-cli-custom-endpoints-design.md` | 无 | 已删除且无保全要求 | 历史设计方案 | 对应实现已入库并经测试验证，方案无单独保全要求 |
| 27 | `gateway/platforms/api_server.py` | `gateway/platforms/api_server.py` | 原路径保留 | `tests/gateway/test_message_api.py`, `test_api_server_bind_guard.py` | /message 路由挂载、双栈 IPv4/IPv6 绑定标准化 |
| 28 | `gateway/platforms/api_server_openai_routes.py` | `gateway/platforms/api_server_openai_routes.py` | 迁移且有等价证据 | `tests/gateway/test_api_server.py` | OpenAI 格式路由已重构为 Siblings，行为等价 |
| 29 | `gateway/platforms/api_server_runs.py` | `gateway/platforms/api_server_runs.py` | 迁移且有等价证据 | `tests/gateway/test_api_server_runs.py` | Runs 异步运行管理模块，保持等价 |
| 30 | `gateway/platforms/base.py` | `gateway/platforms/base.py` | 原路径保留 | `tests/gateway/test_qqbot.py` | 扩展 `SUPPORTED_DOCUMENT_TYPES` 与文本注入判定 |
| 31 | `gateway/platforms/qqbot/adapter.py` | `gateway/platforms/qqbot/adapter.py` | 原路径保留 | `tests/gateway/test_qqbot.py` (72✓) | 附件下载缓存、文本注入、审批流、图片视觉路由 |
| 32 | `gateway/run.py` | `gateway/run.py` | 原路径保留 | `tests/gateway/test_gateway.py` | 网关入口与多平台调度挂载 |
| 33 | `hermes_cli/__init__.py` | `hermes_cli/__init__.py` | 原路径保留 | `tests/hermes_cli/test_config.py` | 模块根导出 |
| 34 | `hermes_cli/auth.py` | `hermes_cli/auth.py` | 原路径保留 | `tests/hermes_cli/test_auth_commands.py` | Google OAuth token 存储与鉴权集成 |
| 35 | `hermes_cli/auth_commands.py` | `hermes_cli/auth_commands.py` | 原路径保留 | `tests/hermes_cli/test_auth_commands.py` | 交互式 `hermes auth login google-gemini-cli` |
| 36 | `hermes_cli/cli_commands_mixin.py` | `hermes_cli/cli_commands_mixin.py` | 原路径保留 | `tests/hermes_cli/test_config.py` | CLI 辅助命令混入 |
| 37 | `hermes_cli/commands.py` | `hermes_cli/commands.py` | 原路径保留 | `tests/hermes_cli/test_config.py` | 统一命令注册调度 |
| 38 | `hermes_cli/config_defaults.py` | `hermes_cli/config_defaults.py` | 原路径保留 | `tests/hermes_cli/test_config.py` (172✓) | `google-gemini-cli` 与 `message_api` 默认项 |
| 39 | `hermes_cli/main.py` | `hermes_cli/main.py` | 原路径保留 | `tests/hermes_cli/test_config.py` | 入口分发与主逻辑 |
| 40 | `hermes_cli/main_install_repair.py` | `hermes_cli/main_install_repair.py` | 原路径保留 | `tests/hermes_cli/test_config.py` | 安装修复与依赖自愈向导 |
| 41 | `hermes_cli/main_provider_setup.py` | `hermes_cli/main_provider_setup.py` | 原路径保留 | `tests/hermes_cli/test_runtime_provider_resolution.py` | 提供方交互式选择与配置向导 |
| 42 | `hermes_cli/model_setup_flows.py` | `hermes_cli/model_setup_flows.py` | 原路径保留 | `tests/hermes_cli/test_runtime_provider_resolution.py` | 包含 Gemini OAuth / Code Assist 向导步骤 |
| 43 | `hermes_cli/models.py` | `hermes_cli/models.py` | 原路径保留 | `tests/hermes_cli/test_runtime_provider_resolution.py` | 模型定义映射与参数配置 |
| 44 | `hermes_cli/runtime_provider.py` | `hermes_cli/runtime_provider.py` | 原路径保留 | `tests/hermes_cli/test_runtime_provider_resolution.py` (102✓) | 自定义 provider 优先预占与 canonical 解析 |
| 45 | `hermes_cli/runtime_provider_custom.py` | `hermes_cli/runtime_provider_custom.py` | 原路径保留 | `tests/hermes_cli/test_runtime_provider_resolution.py` | 自定义端点运行时适配与分发 |
| 46 | `hermes_cli/subcommands/logout.py` | `hermes_cli/subcommands/logout.py` | 原路径保留 | `tests/hermes_cli/test_auth_commands.py` | 清理已持久化的 Google OAuth 凭据 |
| 47 | `hermes_cli/update_cmd_deps.py` | `hermes_cli/update_cmd.py` + `hermes_cli/old_updater_deps.py` | 迁移且有等价证据 | `tests/hermes_cli/test_update_missing_configured_deps.py`, `tests/hermes_cli/test_windows_update_restart_reconciliation.py` | 旧依赖修复路径改由更新流程接管；Windows 重启协调另有真实测试，不能仅凭路径存在断言所有旧行为等价 |
| 48 | `plugins/platforms/feishu/adapter.py` | `plugins/platforms/feishu/adapter.py` | 迁移且有等价证据 | 上游平台单元测试 | 飞书适配器事件处理已与上游原生实现等价统一 |
| 49 | `pyproject.toml` | `pyproject.toml` | 原路径保留 | `uv lock --check` | 依赖范围约束与锁版本同步 |
| 50 | `run_agent.py` | `run_agent.py` | 原路径保留 | `tests/agent/test_run_agent.py` | 窄腰入口保持，保持与 agent/turn 体系协同 |
| 51 | `tests/agent/test_credential_pool.py` | `tests/agent/test_credential_pool.py` | 原路径保留 | 单元测试通过 (7✓) | 验证 OAuth 凭证池轮询、刷新与失效标记 |
| 52 | `tests/agent/test_gemini_cloudcode.py` | `tests/agent/test_gemini_cloudcode.py` | 原路径保留 | 199 项测试通过 (199✓) | 验证 Code Assist 全套模拟协议与会话控制 |
| 53 | `tests/agent/test_gemini_endpoints.py` | `tests/agent/test_gemini_endpoints.py` | 原路径保留 | 90 项测试通过 (90✓) | 验证反向代理、端点映射与错误隔离 |
| 54 | `tests/agent/test_run_agent.py` | `tests/agent/test_run_agent.py` | 原路径保留 | 单元测试通过 | Agent 循环核心逻辑回归 |
| 55 | `tests/gateway/test_api_server.py` | `tests/gateway/test_api_server.py` | 原路径保留 | 单元测试通过 | API Server 核心接口回归 |
| 56 | `tests/gateway/test_api_server_bind_guard.py` | `tests/gateway/test_api_server_bind_guard.py` | 原路径保留 | 11 项测试通过 (11✓) | 验证 `host: "dual"` 与双栈单栈隔离 |
| 57 | `tests/gateway/test_api_server_toolset.py` | `tests/gateway/test_api_server_toolset.py` | 原路径保留 | 12 项测试通过 (12✓) | 验证 `peer_messaging` 与 `hermes-api-server` 工具挂载 |
| 58 | `tests/gateway/test_qqbot.py` | `tests/gateway/test_qqbot.py` | 原路径保留 | 72 项测试通过 (72✓) | 验证 QQBot 附件注入、审批流与视觉流 |
| 59 | `tests/hermes_cli/test_auth_commands.py` | `tests/hermes_cli/test_auth_commands.py` | 原路径保留 | 单元测试通过 | 验证 CLI 认证命令与登出 |
| 60 | `tests/hermes_cli/test_editable_install_metadata.py` | `tests/hermes_cli/test_source_launcher_publication.py` | 迁移且有等价证据 | `test_source_launcher_publication.py` (4✓) | 源码/Editable 模式安装检测迁移至源码启动器测试 |
| 61 | `tests/hermes_cli/test_gemini_provider.py` | `tests/hermes_cli/test_gemini_provider.py` | 原路径保留 | 单元测试通过 | 验证 Gemini 提供方解析 |
| 62 | `tests/hermes_cli/test_gquota_command.py` | `tests/hermes_cli/test_gquota_command.py` | 原路径保留 | 单元测试通过 | 验证配额查询输出与脱敏 |
| 63 | `tests/hermes_cli/test_model_provider_persistence.py` | `tests/hermes_cli/test_model_provider_persistence.py` | 原路径保留 | 单元测试通过 | 验证提供方持久化写入 |
| 64 | `tests/hermes_cli/test_runtime_provider_resolution.py` | `tests/hermes_cli/test_runtime_provider_resolution.py` | 原路径保留 | 102 项测试通过 (102✓) | 验证自定义端点预占解析及 Fallback |
| 65 | `tests/hermes_cli/test_subcommands_batch.py` | `tests/hermes_cli/test_subcommands_batch.py` | 原路径保留 | 单元测试通过 | 验证批处理子命令 |
| 66 | `tests/tools/test_hermes_message_tool.py` | `tests/tools/test_hermes_message_tool.py` | 原路径保留 | 11 项测试通过 (11✓) | 验证 `send_hermes_message` 调用与门禁 |
| 67 | `tests/tools/test_url_safety.py` | `tests/tools/test_url_safety.py` | 原路径保留 | 81 项测试通过 (81✓) | 验证 QQ 域名 Fake-IP 白名单与 SSRF 防护 |
| 68 | `tests/tools/test_windows_native_support.py` | `tests/tools/test_windows_native_support.py` | 原路径保留 | 单元测试通过 | 验证 Windows 原生特性与路径支持 |
| 69 | `tools/hermes_message_tool.py` | `tools/hermes_message_tool.py` | 原路径保留 | `tests/tools/test_hermes_message_tool.py` | 跨节点通信工具实现与服务门禁 |
| 70 | `tools/url_safety.py` | `tools/url_safety.py` | 原路径保留 | `tests/tools/test_url_safety.py` | 安全 URL 检查与 Fake-IP 特例放行 |
| 71 | `toolsets.py` | `toolsets.py` | 原路径保留 | `tests/gateway/test_api_server_toolset.py` | 收敛 `_HERMES_CORE_TOOLS`，在 `hermes-api-server` 明确声明 |
| 72 | `uv.lock` | `uv.lock` | 原路径保留 | `uv lock --check` | 依赖锁定文件与上游同步 |
| 73 | `web/src/components/AuthWidget.tsx` | `web/src/components/AuthWidget.tsx` | 原路径保留 | `web` vitest (357✓) | 包含 Google OAuth 登录状态小部件 |
| 74 | `web/src/components/AutoField.tsx` | `web/src/components/AutoField.tsx` | 原路径保留 | `web` vitest (357✓) | 动态表单组件，包含中文字段提示 |
| 75 | `web/src/components/AutomationBlueprints.tsx` | `web/src/components/AutomationBlueprints.tsx` | 原路径保留 | `web` vitest (357✓) | 自动化蓝图国际化支持 |
| 76 | `web/src/components/ChatSessionList.tsx` | `web/src/components/ChatSessionList.tsx` | 原路径保留 | `web` vitest (357✓) | 会话列表多语言支持 |
| 77 | `web/src/components/ChatSidebar.tsx` | `web/src/components/ChatSidebar.tsx` | 原路径保留 | `web/src/components/ChatSidebar.test.tsx` (18✓) | 聊天侧边栏多语言支持 |
| 78 | `web/src/components/ConfirmDialog.tsx` | `web/src/components/ConfirmDialog.tsx` | 原路径保留 | `web` vitest (357✓) | 确认对话框中英文支持 |
| 79 | `web/src/components/HermesConsoleModal.tsx` | `web/src/components/HermesConsoleModal.tsx` | 原路径保留 | `web` vitest (357✓) | 控制台弹窗多语言 |
| 80 | `web/src/components/ModelInfoCard.tsx` | `web/src/components/ModelInfoCard.tsx` | 原路径保留 | `web` vitest (357✓) | 模型详情卡片多语言与端点信息 |
| 81 | `web/src/components/ModelPickerDialog.tsx` | `web/src/components/ModelPickerDialog.tsx` | 原路径保留 | `web` vitest (357✓) | 模型选择器包含 Gemini 选项 |
| 82 | `web/src/components/ModelReloadConfirm.tsx` | `web/src/components/ModelReloadConfirm.tsx` | 原路径保留 | `web` vitest (357✓) | 重载提示本地化 |
| 83 | `web/src/components/OAuthProvidersCard.tsx` | `web/src/components/OAuthProvidersCard.tsx` | 原路径保留 | `web` vitest (357✓) | OAuth 提供方管理卡片 |
| 84 | `web/src/components/ReasoningPicker.tsx` | `web/src/components/ReasoningPicker.tsx` | 原路径保留 | `web` vitest (357✓) | 推理等级选择器本地化 |
| 85 | `web/src/components/SkillEditorDialog.tsx` | `web/src/components/SkillEditorDialog.tsx` | 原路径保留 | `web` vitest (357✓) | 技能编辑对话框本地化 |
| 86 | `web/src/components/ToolsetConfigDrawer.tsx` | `web/src/components/ToolsetConfigDrawer.tsx` | 原路径保留 | `web` vitest (357✓) | 工具集配置抽屉本地化 |
| 87 | `web/src/i18n/en.ts` | `web/src/i18n/en.ts` | 原路径保留 | `web` 生产构建通过 | 英文词条（保留消息密钥及扩展词条） |
| 88 | `web/src/i18n/i18n.test.ts` | `web/src/i18n/i18n.test.ts` | 原路径保留 | `web` vitest (4✓) | i18n 字典覆盖率与 key 匹配契约测试 |
| 89 | `web/src/i18n/localization-behavior.test.tsx` | `web/src/i18n/localization-behavior.test.tsx` | 原路径保留 | `web` vitest (3✓) | Web 端语言动态切换行为与 DOM 渲染契约测试 |
| 90 | `web/src/i18n/pagesEn.ts` | `web/src/i18n/pagesEn.ts` | 原路径保留 | `web` 构建测试通过 | 页面级独立英文词条字典 |
| 91 | `web/src/i18n/pagesTypes.ts` | `web/src/i18n/pagesTypes.ts` | 原路径保留 | 前端类型检查通过 | 页面级独立 i18n 类型声明接口 |
| 92 | `web/src/i18n/pagesZh.ts` | `web/src/i18n/pagesZh.ts` | 原路径保留 | `web` 构建测试通过 | 页面级独立中文词条字典 |
| 93 | `web/src/i18n/types.ts` | `web/src/i18n/types.ts` | 原路径保留 | 前端类型检查 | 前端 i18n 完整类型定义 |
| 94 | `web/src/i18n/zh.ts` | `web/src/i18n/zh.ts` | 原路径保留 | 前端生产构建通过 | 全量简体中文本地化字典 |
| 95 | `web/src/lib/messaging-field-localization.ts` | `web/src/pages/ChannelsPage.tsx` | 迁移且有等价证据 | `web` 生产构建通过 | 消息通道字段翻译已内联至 ChannelsPage 及主 i18n |
| 96 | `web/src/pages/AnalyticsPage.tsx` | `web/src/pages/AnalyticsPage.tsx` | 原路径保留 | 前端生产构建通过 | 分析页面中文化 |
| 97 | `web/src/pages/ChannelsPage.test.ts` | `web/src/pages/ChannelsPage.test.ts` | 原路径保留 | `web` vitest (2✓) | 频道页面辅助测试 |
| 98 | `web/src/pages/ChannelsPage.tsx` | `web/src/pages/ChannelsPage.tsx` | 原路径保留 | 前端生产构建通过 | 通道配置页面（包含 QQBot/微信/API Server 配置） |
| 99 | `web/src/pages/ChatPage.tsx` | `web/src/pages/ChatPage.tsx` | 原路径保留 | `web/src/pages/ChatPage.test.tsx` (14✓) | 对话主页面多语言及 PTY 重连 |
| 100 | `web/src/pages/CronPage.tsx` | `web/src/pages/CronPage.tsx` | 原路径保留 | 前端生产构建通过 | 定时任务页面多语言 |
| 101 | `web/src/pages/EnvPage.tsx` | `web/src/pages/EnvPage.tsx` | 原路径保留 | 前端生产构建通过 | 环境变量页面多语言 |
| 102 | `web/src/pages/FilesPage.tsx` | `web/src/pages/FilesPage.tsx` | 原路径保留 | 前端生产构建通过 | 文件管理页面多语言 |
| 103 | `web/src/pages/McpPage.tsx` | `web/src/pages/McpPage.tsx` | 原路径保留 | 前端生产构建通过 | MCP 页面多语言 |
| 104 | `web/src/pages/ModelsPage.tsx` | `web/src/pages/ModelsPage.tsx` | 原路径保留 | 前端生产构建通过 | 模型管理页面多语言 |
| 105 | `web/src/pages/PairingPage.tsx` | `web/src/pages/PairingPage.tsx` | 原路径保留 | 前端生产构建通过 | 设备配对页面多语言 |
| 106 | `web/src/pages/PluginsPage.tsx` | `web/src/pages/PluginsPage.tsx` | 原路径保留 | 前端生产构建通过 | 插件管理页面多语言 |
| 107 | `web/src/pages/ProfileBuilderPage.tsx` | `web/src/pages/ProfileBuilderPage.tsx` | 原路径保留 | 前端生产构建通过 | Profile 构建器多语言 |
| 108 | `web/src/pages/ProfilesPage.tsx` | `web/src/pages/ProfilesPage.tsx` | 原路径保留 | 前端生产构建通过 | 多 Profile 页面多语言 |
| 109 | `web/src/pages/SessionsPage.test.tsx` | `web/src/pages/SessionsPage.test.tsx` | 原路径保留 | `web/src/pages/SessionsPage.test.tsx` (2✓) | 会话页面多 Profile 隔离契约测试 |
| 110 | `web/src/pages/SessionsPage.tsx` | `web/src/pages/SessionsPage.tsx` | 原路径保留 | 前端生产构建通过 | 会话历史页面多语言 |
| 111 | `web/src/pages/SkillsPage.tsx` | `web/src/pages/SkillsPage.tsx` | 原路径保留 | 前端生产构建通过 | 技能商店/管理页面多语言 |
| 112 | `web/src/pages/SystemPage.tsx` | `web/src/pages/SystemPage.tsx` | 原路径保留 | 前端生产构建通过 | 系统设置页面多语言 |
| 113 | `web/src/pages/WebhooksPage.tsx` | `web/src/pages/WebhooksPage.tsx` | 原路径保留 | 前端生产构建通过 | Webhook 页面多语言 |
| 114 | `website/docs/reference/optional-skills-catalog.md` | `website/docs/reference/optional-skills-catalog.md` | 原路径保留 | 文档内容核对 | 扩展技能文档更新 |
| 115 | `website/docs/user-guide/features/api-server.md` | `website/docs/user-guide/features/api-server.md` | 原路径保留 | 文档内容核对 | 详细记录 /message 接口契约、权限分级与 SQLite 配置说明 |
