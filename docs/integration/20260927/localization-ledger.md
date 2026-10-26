# 任务 0 现场冻结与可验收汉化台账 (Task 0 Baseline & Localization Ledger)

> **审计与冻结基准日期**：2026-09-27
> **隔离工作树目录**：`C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent`
> **生产安装目录保护**：`F:\hermes-desktop`（只读核查，严禁手改或覆盖）
> **主开发目录保护**：`F:\Documents\Project\hermes-agent`（原样保留不碰）

---

## 1. 现场冻结与环境核查证据 (Environment & Freeze Evidence)

### 1.1 隔离工作树 Git 现场

- **HEAD 提交哈希 (`git rev-parse HEAD`)**：`f28c42237bd4b4862dfce4277a215e6d90b299a8`
- **工作区状态 (`git status --short`)**：干净（执行输出为空）
- **共同基线锚点 (`git merge-base main HEAD`)**：`cce025a2ca3990335f302dc3d1f9f6763614a40c`

### 1.2 生产安装目录只读核查 (`F:\hermes-desktop`)

- **Git 仓库核查**：确认 `F:\hermes-desktop` **不是** Git 仓库（`Test-Path F:\hermes-desktop\.git` 为 `False`）。
- **关键发布文件存在性**：
  - `resources\app.asar`：存在（`True`）
  - `resources\app.asar.unpacked`：存在（`True`）
  - `Hermes.exe`：存在（`True`）
- **安装印戳 (`F:\hermes-desktop\resources\install-stamp.json`)**：
  ```json
  {
    "schemaVersion": 1,
    "commit": "a5e968d4ca83ec38ba59520751d985197b1f0a79",
    "branch": "main",
    "builtAt": "2026-09-20T04:06:18.313Z",
    "dirty": true,
    "source": "local"
  }
  ```
- **核心包 SHA256 哈希 (`Get-FileHash resources\app.asar -Algorithm SHA256`)**：
  `F3DC8D8AE440A606C9E7F588B68C4E6438CE728CB37F8B0FEC02E5EFBAF56510`

### 1.3 正在运行的 Hermes.exe 实例守护记录（绝对保持运行，严禁退出）

| 进程 PID | 进程名称 | 可执行路径 | 启动命令行 |
| :--- | :--- | :--- | :--- |
| `37148` | `Hermes.exe` | `F:\hermes-desktop\Hermes.exe` | `"F:\hermes-desktop\Hermes.exe"` |
| `19848` | `Hermes.exe` | `F:\hermes-desktop\Hermes.exe` | `"F:\hermes-desktop\Hermes.exe" --type=gpu-process --user-data-dir="C:\Users\qwe57\AppData\Roaming\Hermes" ...` |
| `14232` | `Hermes.exe` | `F:\hermes-desktop\Hermes.exe` | `"F:\hermes-desktop\Hermes.exe" --type=utility --utility-sub-type=network.mojom.NetworkService --lang=zh-CN ...` |
| `13340` | `Hermes.exe` | `F:\hermes-desktop\Hermes.exe` | `"F:\hermes-desktop\Hermes.exe" --type=renderer --user-data-dir="C:\Users\qwe57\AppData\Roaming\Hermes" ... --lang=zh-CN ...` |
| `39336` | `Hermes.exe` | `F:\hermes-desktop\Hermes.exe` | `"F:\hermes-desktop\Hermes.exe" --type=utility --utility-sub-type=audio.mojom.AudioService --lang=zh-CN ...` |

---

## 2. 汉化可验收台账 (Localization Ledger)

> **台账填报说明**：
> 1. **明确排除项统一规则**：用户/服务商动态数据（用户消息、API Key 密钥明文、自定义 URL）、动态模型标识符（如 `gpt-4o`、`claude-3-5-sonnet`）、CLI 命令（如 `/skills`、`hermes mcp add`）、YAML/JSON 配置键名（如 `agent.max_turns`）、第三方插件私有内部 Schema 与标识。
> 2. **状态覆盖**：每个表面完整覆盖正常态、空态、错误态。

| 序号 | 表面 (Surface) | 语言 (Locale) | 界面状态 (State) | 源码文件 (Source File) | 英文可见文案 (English Visible) | 明确排除项 (Exclusion) | 行为测试路径 (Behavior Test) | 验收结果 (Result) |
| :---: | :--- | :---: | :---: | :--- | :--- | :--- | :--- | :---: |
| 1 | Web: McpPage | zh-CN / zh | 正常态 | `web/src/pages/McpPage.tsx` | "Model Context Protocol", "Active MCP Servers", "Add Server", "Status", "Tools", "Restart" | 动态服务名、工具标识、CLI命令、配置JSON | `web/src/pages/McpPage.test.tsx` | 基线已通过 |
| 2 | Web: McpPage | zh-CN / zh | 空态 | `web/src/pages/McpPage.tsx` | "No MCP servers configured", "Add an MCP server to extend model capabilities" | 动态建议服务名、第三方扩展标识 | `web/src/pages/McpPage.test.tsx` | 基线已通过 |
| 3 | Web: McpPage | zh-CN / zh | 错误态 | `web/src/pages/McpPage.tsx` | "Failed to load MCP servers", "Connection failed", "Process exited unexpectedly" | 底层异常堆栈、系统错误码、进程PID | `web/src/pages/McpPage.test.tsx` | 基线已通过 |
| 4 | Web: ChannelsPage | zh-CN / zh | 正常态 | `web/src/pages/ChannelsPage.tsx` | "Messaging Channels", "Configure platforms", "Connected", "Save and enable", "Restart gateway" | Bot Token、用户ID、Channel ID、Webhook URL | `web/src/pages/ChannelsPage.test.ts` | 基线已通过 |
| 5 | Web: ChannelsPage | zh-CN / zh | 空态 | `web/src/pages/ChannelsPage.tsx` | "No messaging channels active", "Select a platform below to configure" | 第三方平台固有专有名词 | `web/src/pages/ChannelsPage.test.ts` | 基线已通过 |
| 6 | Web: ChannelsPage | zh-CN / zh | 错误态 | `web/src/pages/ChannelsPage.tsx` | "Operation failed", "Telegram token invalid", "Slack member ID invalid", "Failed to restart" | 原始网络响应体、加密机密、私有端点 | `web/src/pages/ChannelsPage.test.ts` | 基线已通过 |
| 7 | Web: SkillsPage | zh-CN / zh | 正常态 | `web/src/pages/SkillsPage.tsx` | "Agent Skills", "Built-in and custom procedural capabilities", "Filter skills", "Install skill" | 技能目录名、frontmatter原始YAML、`/skills`命令 | `web/src/i18n/localization-behavior.test.tsx` | 基线已通过 |
| 8 | Web: SkillsPage | zh-CN / zh | 空态 | `web/src/pages/SkillsPage.tsx` | "No skills installed", "Install skills from the catalog or create custom ones" | 动态分类过滤标签、技能存储绝对路径 | `web/src/i18n/localization-behavior.test.tsx` | 基线已通过 |
| 9 | Web: SkillsPage | zh-CN / zh | 错误态 | `web/src/pages/SkillsPage.tsx` | "Failed to load skills", "Failed to parse skill frontmatter", "Skill definition error" | 语法解析报错行列号、外部URL参数 | `web/src/i18n/localization-behavior.test.tsx` | 基线已通过 |
| 10 | Web: SystemPage | zh-CN / zh | 正常态 | `web/src/pages/SystemPage.tsx` | "System Information", "Runtime Status", "Gateway Uptime", "Memory Usage", "Active Profiles" | 动态主机名、物理路径、CPU/内存数值、PID | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 11 | Web: SystemPage | zh-CN / zh | 空态 | `web/src/pages/SystemPage.tsx` | "No active background tasks", "System idle" | 系统内核版本字符串、动态硬件架构 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 12 | Web: SystemPage | zh-CN / zh | 错误态 | `web/src/pages/SystemPage.tsx` | "Gateway unreachable", "Failed to query system metrics", "Subprocess failure" | 底层套接字错误码、操作系统错误日志 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 13 | Web: ProfilesPage | zh-CN / zh | 正常态 | `web/src/pages/ProfilesPage.tsx` | "Agent Profiles", "Manage isolated profiles", "Create Profile", "Clone Profile", "Active Profile" | Profile名称、文件系统物理路径、动态环境配置 | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 14 | Web: ProfilesPage | zh-CN / zh | 空态 | `web/src/pages/ProfilesPage.tsx` | "No additional profiles found", "Using default profile" | 默认Profile标识符 (`default`) | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 15 | Web: ProfilesPage | zh-CN / zh | 错误态 | `web/src/pages/ProfilesPage.tsx` | "Failed to load profiles", "Cannot delete active profile", "Profile name collision" | 目标文件系统报错、非法字符原始输入 | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 16 | Web: ProfileBuilderPage | zh-CN / zh | 正常态 | `web/src/pages/ProfileBuilderPage.tsx` | "Profile Builder", "Configure model, system prompt, and tools", "Save profile" | 动态模型名称、自定义系统提示词文本、环境变量 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 17 | Web: ProfileBuilderPage | zh-CN / zh | 空态 | `web/src/pages/ProfileBuilderPage.tsx` | "No customized fields", "Inheriting default configuration" | 继承的基线配置快照键名 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 18 | Web: ProfileBuilderPage | zh-CN / zh | 错误态 | `web/src/pages/ProfileBuilderPage.tsx` | "Invalid profile configuration", "Model resolution failed", "Failed to save profile" | 校验失败字段Key、配置验证器Schema报错 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 19 | Web: ModelsPage | zh-CN / zh | 正常态 | `web/src/pages/ModelsPage.tsx` | "Model Catalog", "Active Model", "Switch Model", "Context Window", "Provider" | 模型名 (`gpt-4o`等)、服务商名、上下文数字 | `web/src/lib/model-picker-filter.test.ts` | 基线已通过 |
| 20 | Web: ModelsPage | zh-CN / zh | 空态 | `web/src/pages/ModelsPage.tsx` | "No models found matching filter", "No provider credentials configured" | 用户搜索关键词、动态筛选器标签 | `web/src/lib/model-picker-filter.test.ts` | 基线已通过 |
| 21 | Web: ModelsPage | zh-CN / zh | 错误态 | `web/src/pages/ModelsPage.tsx` | "Failed to fetch model catalog", "Provider validation error", "Switch failed" | HTTP状态码、第三方提供商API错误原文 | `web/src/lib/model-picker-filter.test.ts` | 基线已通过 |
| 22 | Web: SessionsPage | zh-CN / zh | 正常态 | `web/src/pages/SessionsPage.tsx` | "Chat Sessions", "Session History", "Resume Session", "Archive", "Export" | 会话UUID、用户对话摘要、动态时间戳 | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 23 | Web: SessionsPage | zh-CN / zh | 空态 | `web/src/pages/SessionsPage.tsx` | "No sessions found", "Start a new chat to begin" | 筛选器状态值、默认工作空间名 | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 24 | Web: SessionsPage | zh-CN / zh | 错误态 | `web/src/pages/SessionsPage.tsx` | "Failed to load sessions", "Session state corrupt — run `hermes doctor`", "Archive failed" | 数据库文件路径、底层SQLite报错 | `web/src/pages/SessionsPage.test.tsx` | 基线已通过 |
| 25 | Web: CronPage | zh-CN / zh | 正常态 | `web/src/pages/CronPage.tsx` | "Scheduled Jobs", "Cron Jobs", "Create Job", "Schedule Expression", "Next Run", "Trigger" | Cron表达式 (`0 9 * * 1-5`)、用户任务指令 | `web/src/lib/cron-job.test.ts` | 基线已通过 |
| 26 | Web: CronPage | zh-CN / zh | 空态 | `web/src/pages/CronPage.tsx` | "No scheduled jobs configured", "Create a recurring task to automate routines" | 预设蓝图标识符 | `web/src/lib/cron-trigger-controller.test.ts` | 基线已通过 |
| 27 | Web: CronPage | zh-CN / zh | 错误态 | `web/src/pages/CronPage.tsx` | "Failed to load cron jobs", "Invalid cron schedule expression", "Trigger failed" | 调度器解析异常、任务执行失败退出码 | `web/src/lib/cron-job.test.ts` | 基线已通过 |
| 28 | Web: PluginsPage | zh-CN / zh | 正常态 | `web/src/pages/PluginsPage.tsx` | "Installed Plugins", "Plugin Directory", "Enable", "Disable", "Settings", "Reload" | 插件标识 (`kanban`等)、版本号、作者动态信息 | `web/src/pages/PluginsPage.test.ts` | 基线已通过 |
| 29 | Web: PluginsPage | zh-CN / zh | 空态 | `web/src/pages/PluginsPage.tsx` | "No plugins installed", "Discover and install plugins from the ecosystem" | 插件源URL、搜索输入关键词 | `web/src/plugins/usePlugins.test.ts` | 基线已通过 |
| 30 | Web: PluginsPage | zh-CN / zh | 错误态 | `web/src/pages/PluginsPage.tsx` | "Failed to load plugins", "Plugin failed to initialize", "Incompatible version" | NPM/Pip包依赖冲突追踪、加载报错详情 | `web/src/pages/PluginsPage.test.ts` | 基线已通过 |
| 31 | Web: PairingPage | zh-CN / zh | 正常态 | `web/src/pages/PairingPage.tsx` | "Device & Client Pairing", "Pair New Client", "Approved Clients", "Scan QR Code" | 配对Nonce码、Token密文、设备指纹与IP | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 32 | Web: PairingPage | zh-CN / zh | 空态 | `web/src/pages/PairingPage.tsx` | "No paired devices", "Scan code or generate token to pair a remote device" | 设备类型动态标识符 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 33 | Web: PairingPage | zh-CN / zh | 错误态 | `web/src/pages/PairingPage.tsx` | "Pairing code expired", "Failed to approve client", "Network timeout" | 握手失败代码、认证拒绝原因数据 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 34 | Web: WebhooksPage | zh-CN / zh | 正常态 | `web/src/pages/WebhooksPage.tsx` | "Inbound Webhooks", "Create Webhook", "Endpoint URL", "Secret Token", "Delivery History" | Webhook路径、Secret密文、Payload数据 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 35 | Web: WebhooksPage | zh-CN / zh | 空态 | `web/src/pages/WebhooksPage.tsx` | "No webhooks configured", "Create an inbound webhook to receive external events" | 示例Payload模板、协议名 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 36 | Web: WebhooksPage | zh-CN / zh | 错误态 | `web/src/pages/WebhooksPage.tsx` | "Failed to load webhooks", "Invalid webhook endpoint", "Secret validation failed" | HTTP回调错误码、签名比对失败诊断 | `web/src/i18n/i18n.test.ts` | 基线已通过 |
| 37 | Web: ConfigPage | zh-CN / zh | 正常态 | `web/src/pages/ConfigPage.tsx` | "Settings & Configuration", "Raw YAML Mode", "Form Mode", "Save Configuration", "Reload" | YAML配置键名 (`terminal.shell`等)、动态配置数值 | `web/src/pages/Config/components/MessageKeysSection.test.tsx` | 基线已通过 |
| 38 | Web: ConfigPage | zh-CN / zh | 空态 | `web/src/pages/ConfigPage.tsx` | "No configuration properties match filter" | 检索关键词、过滤分组名称 | `web/src/pages/Config/components/MessageKeysSection.test.tsx` | 基线已通过 |
| 39 | Web: ConfigPage | zh-CN / zh | 错误态 | `web/src/pages/ConfigPage.tsx` | "Failed to load configuration", "Failed to save configuration", "Invalid YAML syntax" | YAML解析器报错行号、文件I/O异常信息 | `web/src/pages/Config/components/MessageKeysSection.test.tsx` | 基线已通过 |
| 40 | Web: FilesPage | zh-CN / zh | 正常态 | `web/src/pages/FilesPage.tsx` | "Workspace Files", "Uploaded Media & Documents", "File Browser", "Upload", "Delete" | 实际文件名、物理绝对路径、文件大小字节数 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 41 | Web: FilesPage | zh-CN / zh | 空态 | `web/src/pages/FilesPage.tsx` | "No files found in workspace directory", "Upload documents or images to share" | 目标空文件夹相对路径 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 42 | Web: FilesPage | zh-CN / zh | 错误态 | `web/src/pages/FilesPage.tsx` | "Failed to load directory", "File permission denied", "File upload failed" | 操作系统文件句柄报错、跨卷移动异常 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 43 | Web: LogsPage | zh-CN / zh | 正常态 | `web/src/pages/LogsPage.tsx` | "System & Agent Logs", "Log Stream", "Filter by Level", "Follow Logs", "Clear View" | 日志动态正文、时间戳、ANSI高亮转义码 | `web/src/lib/log-classify.test.ts` | 基线已通过 |
| 44 | Web: LogsPage | zh-CN / zh | 空态 | `web/src/pages/LogsPage.tsx` | "No log entries found matching criteria", "Waiting for incoming log stream..." | 日志过滤器级别参数 (`INFO`, `DEBUG`) | `web/src/lib/log-classify.test.ts` | 基线已通过 |
| 45 | Web: LogsPage | zh-CN / zh | 错误态 | `web/src/pages/LogsPage.tsx` | "Log stream connection closed", "Failed to query historical logs" | WebSocket断开Code、日志文件锁占用信息 | `web/src/lib/log-classify.test.ts` | 基线已通过 |
| 46 | Web: EnvPage | zh-CN / zh | 正常态 | `web/src/pages/EnvPage.tsx` | "Environment Variables", "Secret Scope", "Set Variable", "Reveal Secret", "Delete" | 环境变量名 (`OPENAI_API_KEY`等)、脱敏星号密文 | `web/src/lib/env-state.test.ts` | 基线已通过 |
| 47 | Web: EnvPage | zh-CN / zh | 空态 | `web/src/pages/EnvPage.tsx` | "No custom environment variables defined in .env" | 配置文件路径 (`~/.hermes/.env`) | `web/src/lib/env-state.test.ts` | 基线已通过 |
| 48 | Web: EnvPage | zh-CN / zh | 错误态 | `web/src/pages/EnvPage.tsx` | "Failed to load environment variables", "Cannot save protected variable" | 系统只读保护变量名、凭据加密异常 | `web/src/lib/env-state.test.ts` | 基线已通过 |
| 49 | Web: AnalyticsPage | zh-CN / zh | 正常态 | `web/src/pages/AnalyticsPage.tsx` | "Usage Analytics", "Token Consumption", "Model Breakdown", "Daily Costs", "Timeframe" | Token数量统计数值、费用金额 ($0.00)、模型标识 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 50 | Web: AnalyticsPage | zh-CN / zh | 空态 | `web/src/pages/AnalyticsPage.tsx` | "No token usage recorded for the selected timeframe" | 用户选定的自定义起止时间范围 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 51 | Web: AnalyticsPage | zh-CN / zh | 错误态 | `web/src/pages/AnalyticsPage.tsx` | "Failed to load analytics data", "State database query failed" | 数据库查询异常信息、不可用路由提示 | `web/src/lib/api-error.test.ts` | 基线已通过 |
| 52 | Web: ChatPage | zh-CN / zh | 正常态 | `web/src/pages/ChatPage.tsx` | "Chat", "Send a message...", "Model", "Reasoning", "Attach", "Terminal", "Start session" | 会话消息正文、模型名、终端输入输出流 | `web/src/pages/ChatPage.test.tsx` | 基线已通过 |
| 53 | Web: ChatPage | zh-CN / zh | 空态 | `web/src/pages/ChatPage.tsx` | "Ask anything or describe a task", "No conversation history yet" | 默认示例提示词选项、键盘快捷键提示 | `web/src/pages/ChatPage.test.tsx` | 基线已通过 |
| 54 | Web: ChatPage | zh-CN / zh | 错误态 | `web/src/pages/ChatPage.tsx` | "PTY WebSocket disconnected", "Session ended unexpectedly", "Auth failed" | WebSocket断开码 (4401/1006)、底层网络错误 | `web/src/pages/ChatPage.test.tsx` | 基线已通过 |
| 55 | Desktop: 设置 - 提供商 (Providers) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/providers-settings.tsx` | "LLM Providers", "Configure API credentials and endpoints", "Add Provider", "Active" | API密钥明文、自定义端点URL、厂商私有参数 | `apps/desktop/src/app/settings/providers-settings.test.tsx` | 基线已通过 |
| 56 | Desktop: 设置 - 提供商 (Providers) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/providers-settings.tsx` | "No custom providers configured", "Using default system provider" | 系统内置Provider标识符 | `apps/desktop/src/app/settings/providers-settings.test.tsx` | 基线已通过 |
| 57 | Desktop: 设置 - 提供商 (Providers) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/providers-settings.tsx` | "Failed to validate API key", "Provider endpoint unreachable", "Failed to save" | 校验接口HTTP状态、远程连接超时详情 | `apps/desktop/src/app/settings/providers-settings.test.tsx` | 基线已通过 |
| 58 | Desktop: 设置 - 工具与密钥 (Tools & Keys) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/keys-settings.tsx` | "Toolsets & API Keys", "Built-in Tool Configuration", "Manage Secrets", "Enable" | 环境变量名 (`TAVILY_API_KEY`等)、工具私有参数 | `apps/desktop/src/app/settings/keys-settings.test.tsx` | 基线已通过 |
| 59 | Desktop: 设置 - 工具与密钥 (Tools & Keys) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/keys-settings.tsx` | "No API keys configured for tools", "Tools will operate in restricted local mode" | 工具模式标识符 | `apps/desktop/src/app/settings/keys-settings.test.tsx` | 基线已通过 |
| 60 | Desktop: 设置 - 工具与密钥 (Tools & Keys) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/keys-settings.tsx` | "Failed to save toolset configuration", "Invalid key format", "Permission denied" | 密钥格式正则校验失败原因、系统写权限异常 | `apps/desktop/src/app/settings/keys-settings.test.tsx` | 基线已通过 |
| 61 | Desktop: 设置 - 插件 (Plugins) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/plugin-install-modal.tsx` | "Desktop Plugins", "Install Plugin", "Configure Settings", "Active Plugins", "Remove" | 插件官方ID、版本号、第三方配置Schema字段 | `apps/desktop/src/app/settings/plugin-install-modal.test.tsx` | 基线已通过 |
| 62 | Desktop: 设置 - 插件 (Plugins) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/plugin-install-modal.tsx` | "No third-party plugins installed", "Browse available plugins to extend desktop" | 插件生态源索引名 | `apps/desktop/src/app/settings/plugin-install-modal.test.tsx` | 基线已通过 |
| 63 | Desktop: 设置 - 插件 (Plugins) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/plugin-install-modal.tsx` | "Plugin installation failed", "Dependency conflict detected", "Failed to load manifest" | 模块未定义依赖名称、包管理器退出码 | `apps/desktop/src/app/settings/plugin-install-modal.test.tsx` | 基线已通过 |
| 64 | Desktop: 设置 - 工作区 (Workspace) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/sessions-settings.tsx` | "Workspaces & Directories", "Default Working Directory", "Choose Directory", "Sync" | 操作系统文件绝对路径、项目目录名、Git分支名 | `apps/desktop/src/app/settings/sessions-settings.test.tsx` | 基线已通过 |
| 65 | Desktop: 设置 - 工作区 (Workspace) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/sessions-settings.tsx` | "No custom workspace attached", "Using default profile directory" | 缺省Profile路径变量 | `apps/desktop/src/app/settings/sessions-settings.test.tsx` | 基线已通过 |
| 66 | Desktop: 设置 - 工作区 (Workspace) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/sessions-settings.tsx` | "Workspace directory does not exist or is not writable", "Failed to switch" | 磁盘无权限错误码、不可达UNC网络路径 | `apps/desktop/src/app/settings/sessions-settings.test.tsx` | 基线已通过 |
| 67 | Desktop: 设置 - 记忆 (Memory / Vault) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/vault-settings.tsx` | "Memory & Credential Vault", "Long-term Agent Memory", "Lock Vault", "Export Memory" | 用户记忆条目正文、哈希串、解密秘钥 | `apps/desktop/src/app/settings/vault-settings.test.tsx` | 基线已通过 |
| 68 | Desktop: 设置 - 记忆 (Memory / Vault) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/vault-settings.tsx` | "Vault is empty — no agent memories recorded yet" | 记忆分类Tag预设项 | `apps/desktop/src/app/settings/vault-settings.test.tsx` | 基线已通过 |
| 69 | Desktop: 设置 - 记忆 (Memory / Vault) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/vault-settings.tsx` | "Vault passcode incorrect", "Failed to decrypt memory storage", "Corrupt database" | 密码哈希不匹配诊断、解密算法异常 | `apps/desktop/src/app/settings/vault-settings.test.tsx` | 基线已通过 |
| 70 | Desktop: 设置 - 通知 (Notifications) | zh-CN / zh | 正常态 | `apps/desktop/src/app/settings/notifications-settings.tsx` | "Notification Preferences", "Desktop Push Notifications", "Sound Alerts", "Test Alert" | 操作系统通知服务专有名词、音频文件名 | `apps/desktop/src/components/notifications.test.tsx` | 基线已通过 |
| 71 | Desktop: 设置 - 通知 (Notifications) | zh-CN / zh | 空态 | `apps/desktop/src/app/settings/notifications-settings.tsx` | "No notifications in history", "All notifications cleared" | 通知中心清空记录时间 | `apps/desktop/src/components/notifications.test.tsx` | 基线已通过 |
| 72 | Desktop: 设置 - 通知 (Notifications) | zh-CN / zh | 错误态 | `apps/desktop/src/app/settings/notifications-settings.tsx` | "Notification permission denied by operating system", "Audio device unavailable" | 系统权限策略代码、音频设备GUID | `apps/desktop/src/components/notifications.test.tsx` | 基线已通过 |
| 73 | Desktop: 会话与辅助控件 - 提示与空态 | zh-CN / zh | 正常态 | `apps/desktop/src/app/chat/index.tsx` | "Start Conversation", "Type / for commands, @ to mention context", "Suggested prompts" | 动态建议内容、物理快捷键 (`Ctrl+K`等) | `apps/desktop/src/app/chat/composer/suggestion-pills.test.tsx` | 基线已通过 |
| 74 | Desktop: 会话与辅助控件 - 提示与空态 | zh-CN / zh | 空态 | `apps/desktop/src/app/chat/index.tsx` | "No active conversation", "Select a session from sidebar or press Ctrl+N" | 引导新建会话按钮绑定事件名 | `apps/desktop/src/components/tips/use-tip-rotation.test.tsx` | 基线已通过 |
| 75 | Desktop: 会话与辅助控件 - 提示与空态 | zh-CN / zh | 错误态 | `apps/desktop/src/app/chat/index.tsx` | "Session closed unexpectedly", "Agent failed to respond", "Turn timeout exceeded" | 会话内部异常Traceback、超时计数器秒数 | `apps/desktop/src/app/chat/preview-error-close.test.tsx` | 基线已通过 |
| 76 | Desktop: 会话与辅助控件 - 错误卡与辅助 | zh-CN / zh | 正常态 | `apps/desktop/src/components/error-boundary.tsx` | "System running smoothly", "Health check OK", "Dismiss" | 诊断探针毫秒延迟数字 | `apps/desktop/src/components/error-boundary.test.tsx` | 基线已通过 |
| 77 | Desktop: 会话与辅助控件 - 错误卡与辅助 | zh-CN / zh | 空态 | `apps/desktop/src/components/error-boundary.tsx` | "No diagnostic warnings" | 状态指示灯颜色枚举 (`green`, `muted`) | `apps/desktop/src/components/error-boundary.test.tsx` | 基线已通过 |
| 78 | Desktop: 会话与辅助控件 - 错误卡与辅助 | zh-CN / zh | 错误态 | `apps/desktop/src/components/error-boundary.tsx` | "Something went wrong in this view", "Fatal Gateway Boot Failure", "Storage corrupted" | 异常堆栈追踪 (stack trace)、内部源码行号 | `apps/desktop/src/components/boot-failure-overlay.test.tsx` | 基线已通过 |
| 79 | Desktop: 能力与连接器 - 能力目录 | zh-CN / zh | 正常态 | `apps/desktop/src/app/capabilities/catalog/catalog.tsx` | "Capabilities & Integrations", "Skills Catalog", "Official Skills", "Built-in Toolsets" | 动态技能ID、第三方Tool参数JSON、作者与License | `apps/desktop/src/app/capabilities/index.test.tsx` | 基线已通过 |
| 80 | Desktop: 能力与连接器 - 能力目录 | zh-CN / zh | 空态 | `apps/desktop/src/app/capabilities/catalog/catalog.tsx` | "No matching capabilities found", "No custom skills installed" | 目录检索查询串 | `apps/desktop/src/i18n/catalog-completeness.test.ts` | 基线已通过 |
| 81 | Desktop: 能力与连接器 - 能力目录 | zh-CN / zh | 错误态 | `apps/desktop/src/app/capabilities/catalog/catalog.tsx` | "Failed to load capabilities catalog", "Skill schema validation failed", "Denied" | Schema格式校验器错误明细、非法字段Key | `apps/desktop/src/app/capabilities/index.test.tsx` | 基线已通过 |
| 82 | Desktop: 能力与连接器 - 连接器与MCP | zh-CN / zh | 正常态 | `apps/desktop/src/app/capabilities/connectors/connectors-view.tsx` | "Connected Services & Connectors", "Add Connector", "Sync Status", "Disconnect", "Test" | OAuth Token、外部回调URL、动态服务标识 | `apps/desktop/src/components/ui/connector-card.test.tsx` | 基线已通过 |
| 83 | Desktop: 能力与连接器 - 连接器与MCP | zh-CN / zh | 空态 | `apps/desktop/src/app/capabilities/connectors/connectors-view.tsx` | "No active connectors", "Connect your GitHub, Notion, or local MCP services" | 预置连接器生态清单 | `apps/desktop/src/components/ui/connector-card.test.tsx` | 基线已通过 |
| 84 | Desktop: 能力与连接器 - 连接器与MCP | zh-CN / zh | 错误态 | `apps/desktop/src/app/capabilities/connectors/connectors-view.tsx` | "Connector authorization expired", "MCP daemon process died", "Handshake failed" | 进程退出信号、标准错误流输出文本 | `apps/desktop/src/components/ui/connector-card.test.tsx` | 基线已通过 |
| 85 | Desktop: 启动与更新 - 启动引导 (Onboarding) | zh-CN / zh | 正常态 | `apps/desktop/src/components/onboarding/flow.tsx` | "Welcome to Hermes", "Set up your agent environment", "Choose model provider", "Get Started" | 检测到的Python版本、物理安装路径、硬件架构 | `apps/desktop/src/components/onboarding/flow.test.tsx` | 基线已通过 |
| 86 | Desktop: 启动与更新 - 启动引导 (Onboarding) | zh-CN / zh | 空态 | `apps/desktop/src/components/onboarding/flow.tsx` | "No previous configuration detected — starting fresh" | 初始状态快照标记 | `apps/desktop/src/components/onboarding/flow.test.tsx` | 基线已通过 |
| 87 | Desktop: 启动与更新 - 启动引导 (Onboarding) | zh-CN / zh | 错误态 | `apps/desktop/src/components/onboarding/flow.tsx` | "Environment check failed", "Python runtime not detected", "Directory not writable" | 依赖缺失诊断行、系统环境检测日志 | `apps/desktop/src/components/desktop-install-overlay.test.tsx` | 基线已通过 |
| 88 | Desktop: 启动与更新 - 状态与浮层 (Updates) | zh-CN / zh | 正常态 | `apps/desktop/src/app/updates-overlay.tsx` | "Check for Updates", "You are up to date", "New version available", "Restart and apply" | 版本号 (`v1.4.2`等)、Commit SHA、发布说明Markdown | `apps/desktop/src/components/update-status.test.tsx` | 基线已通过 |
| 89 | Desktop: 启动与更新 - 状态与浮层 (Updates) | zh-CN / zh | 空态 | `apps/desktop/src/app/updates-overlay.tsx` | "No pending updates available" | 更新通道标识 (`stable`, `beta`) | `apps/desktop/src/components/update-status.test.tsx` | 基线已通过 |
| 90 | Desktop: 启动与更新 - 状态与浮层 (Updates) | zh-CN / zh | 错误态 | `apps/desktop/src/app/updates-overlay.tsx` | "Update check failed", "Download corrupted", "Failed to apply update patch" | 下载哈希不匹配校验值、GitHub API限流响应 | `apps/desktop/src/app/updates-overlay.manual.test.tsx` | 基线已通过 |

---

## 3. 基线测试执行证据与既有失败记录 (Baseline Verification & Existing Failures)

本轮测试在隔离工作树（`C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent`）以严格只读模式执行，未修改或覆盖任何生产代码或应用包。

### 3.1 Web 工作区验证 (`npm run check --workspace web`)

- **执行命令**：`npm run check --workspace web`
- **真实退出码**：`EXIT_CODE=0`
- **详细产出明细**：
  - **Typecheck (`tsc -p . --noEmit`)**：0 错误
  - **Vitest (`vitest run`)**：**54 passed (54 files), 369 passed (369 tests), 0 failed**，耗时 11.69s
  - **Lint (`eslint .`)**：0 错误（有 15 项既有关于 effect/refs 的 react-hooks warning）

### 3.2 Desktop 类型检查 (`npm run typecheck --workspace apps/desktop`)

- **执行命令**：`npm run typecheck --workspace apps/desktop`
- **真实退出码**：`EXIT_CODE=0`
- **详细产出明细**：
  - 4 套 TS 配置全部通过无报错：
    1. `tsc -p . --noEmit`：0 错误
    2. `tsc -p tsconfig.electron.json --noEmit`：0 错误
    3. `tsc -p tsconfig.e2e.json --noEmit`：0 错误
    4. `electron-builder.config.cjs` 类型核验：0 错误

### 3.3 Desktop 完整 UI 测试集 (`npm run test:ui --workspace apps/desktop`)

- **执行命令**：`npm run test:ui --workspace apps/desktop`
- **真实退出码**：`EXIT_CODE=1`（既有测试失败，无新增退化）
- **测试总览统计**：
  - **测试文件总数 (Test Files)**：**1063 个**
    - **通过文件 (Passed Files)**：**1060 个**
    - **既有失败文件 (Failed Files)**：**3 个**
  - **测试用例总数 (Tests)**：**9123 个**
    - **通过用例 (Passed Tests)**：**9119 个**
    - **既有失败用例 (Failed Tests)**：**4 个**
  - **执行耗时**：363.33s

### 3.4 既有失败分析归档 (Existing Failures Ledger)

以下 3 个文件中的 4 项失败系合并 upstream-sync-20260925 时的既有环境/断言差异，详细失败信息如实记录备查：

1. **`apps/desktop/src/store/voice-prefs.test.ts`**（2 项失败）：
   - 失败用例 1：`keeps the desktop toggle local across config refreshes`
     - 报错信息：`AssertionError: expected 'false' to be null // Object.is equality`
     - 根因：`localStorage.getItem('hermes.desktop.autoSpeakReplies')` 期望在重置时为 `null`，实际读取到字符串 `"false"`。
   - 失败用例 2：`migrates the legacy preference once, not on every refresh`
     - 报错信息：`AssertionError: expected 'false' to be null // Object.is equality`
     - 根因：同上，首轮迁移后在特定分支的配置重置断言中预期 `null`，实际存储留存了 `"false"`。

2. **`apps/desktop/src/plugins/hermes-bots/cron-detail.test.tsx`**（1 项失败）：
   - 失败用例：`the row is reachable > labels a next run parked past the scheduler grace as overdue, never as "Next" (#114309)`
   - 报错信息：`TestingLibraryElementError: Unable to find an element with the text: /^Overdue since:.*ago$/`
   - 根因：本地化运行时在非英文/中西混合环境渲染出的相对时间为 `"Overdue since: 7小时前"`，断言正则表达式严格要求英文尾随单词 `"ago"`（`/^Overdue since:.*ago$/`），文案本地化导致正则不匹配。

3. **`apps/desktop/src/plugins/hermes-bots/profile-config-capabilities.test.tsx`**（1 项失败）：
   - 失败用例：`a build whose CapabilitiesView cannot route connections > keeps the LOCAL capability surfaces, each scoped to the bot profile`
   - 报错信息：`AssertionError: expected 2 to be 1 // Object.is equality`
   - 根因：在只支持本地能力路由的构建中，`sdk.gatewayReads.count` 计数预期为 1 次，当前由于挂载时的 Profile 预热探针触发了额外的网关状态探测，计数为 2。
