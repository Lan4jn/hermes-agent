# 2026-10-28 核心定制功能跟踪清单（Feature Ledger）

| 模块类别 | 核心功能点 | 目标文件落点 | 验收与保活标准 | 负责人 |
| :--- | :--- | :--- | :--- | :--- |
| **LLM / Provider** | Google Gemini CLI OAuth 登录与 Token 刷新 | `agent/google_oauth.py`, `hermes_cli/auth_gemini.py` | 支持 OAuth PKCE 登录，自动计算过期时间并安全持久化，不泄露凭据 | Task-25 (Backend) |
| **LLM / Provider** | Gemini CloudCode 与 Code Assist 配额查询 | `agent/gemini_cloudcode_adapter.py`, `agent/google_code_assist.py`, `hermes_cli/cli_commands_mixin.py` | `/gquota` 指令格式化输出配额柱状图，不抛未捕获异常 | Task-25 (Backend) |
| **LLM / Provider** | 动态分档模型与通用思考参数映射 | `agent/gemini_endpoints.py`, `hermes_cli/runtime_provider.py` | 适配 `gemini-3.8-flash-tiered`，支持通用 provider 路由扩展，不强制写死用户默认模型 | Task-25 (Backend) |
| **LLM / Provider** | Custom Provider 配置隔离修复 (P1-2) | `hermes_cli/runtime_provider_custom.py` | 优先提取传入 `config["model"]["base_url"]`，杜绝穿透默认配置破坏 Profile 隔离 | Task-25 (Backend) |
| **跨节点互联** | Message API 核心接口与鉴权 | `gateway/platforms/message_api.py`, `gateway/platforms/message_api_keys.py` | POST `/message` 路由正常响应，支持密钥与远程执行安全策略 | Task-25 (Backend) |
| **跨节点互联** | Node-to-Node 对等通信工具 | `tools/hermes_message_tool.py`, `toolsets.py` | 工具集 `peer_messaging` 导出 `send_hermes_message`，保持上游架构对齐 | Task-25 (Backend) |
| **API 服务治理** | Direct 模式策略全链路透传 (P1-1) | `gateway/platforms/api_server.py`, `gateway/session_api_turn.py`, `gateway/run_turn_runner.py` | 透传 `agent_mode="direct"`，强制执行 `max_iterations=1`、`enabled_toolsets=[]`、跳过上下文与记忆 | Task-25 (Backend) |
| **API 服务治理** | API Server Host 规范化绑定 | `gateway/platforms/api_server.py` | `normalize_api_server_host` 正确解析 `dual`、`::`、`0.0.0.0` 及回退回环地址 | Task-25 (Backend) |
| **平台适配** | QQBot 富媒体附件纠偏与 100KB 切片注入 | `plugins/platforms/qqbot/adapter.py` | 扩展名识别 `.sql/.conf/.properties` 等文本；≤100KB 注入全文，>100KB 注入 `Preview` | Task-25 (Backend) |
| **平台适配** | QQBot 危险指令按钮审批交互 | `plugins/platforms/qqbot/adapter.py` | 按钮渲染支持 `ExecApprovalPrompt`，回调正常通知审批状态 | Task-25 (Backend) |
| **依赖环境** | Windows 平台 PM 环境持久化导入保活 | `gateway/run.py` | `_ensure_windows_gateway_venv_imports` 保活 `committed_venv` site-packages，避免降级为旧环境 | Task-25 (Backend) |
| **桌面端与前端** | Message Keys 管理组件与路由挂载 | `hermes_cli/web_routers/message_keys.py`, `web/src/pages/Config/components/MessageKeysSection.tsx` | Web 仪表盘能增删查改 Message Keys 列表，RPC 契约对齐 | Task-24 (UI/Desktop) |
| **桌面端与前端** | 完整简繁体中文语言包覆盖 | `apps/desktop/src/i18n/zh.ts`, `apps/desktop/src/i18n/zh-hant.ts`, `web/src/i18n/zh.ts`, `web/src/i18n/zh-hant.ts` | 界面词条全部正确国际化，无缺失键造成的白屏或回退英文 | Task-24 (UI/Desktop) |
| **桌面端与前端** | 模型热重载与渠道配置对齐 | `web/src/components/ModelReloadConfirm.tsx`, `web/src/pages/ChannelsPage.tsx`, `web/src/pages/SystemPage.tsx` | 弹窗及列表页面上游结构更新与中文定制共存 | Task-24 (UI/Desktop) |
| **文档** | 网关特性与文档排版中文同步 | `website/i18n/zh-Hans/.../tool-gateway.md` | 保留中文翻译与新上游功能说明 | Task-24 (UI/Desktop) |
