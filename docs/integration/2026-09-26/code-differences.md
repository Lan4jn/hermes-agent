# 2026-09-26 上游移植与 Fork 定制功能差异清单

## 1. 概述与基准拓扑

- **共同基准 (Merge-Base)**: `bc86ff6c4ac8785016d0023f37ad8b119ed120de`
- **Fork 主分支 (`origin/main`)**: `47316a9d1b6e830c01db488c65e51c6b8be55415`
- **上游最新分支 (`upstream/main`)**: `e13b5e71ef` (包含 2026-09-26 最新合并)
- **当前移植候选分支 (`codex/upstream-port-20260925`)**: 工作树处于 `C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent`

---

## 2. 差异对比与逐项归宿表

| 序号 | 功能模块 | Fork 实现文件 (`origin/main`) | 候选分支当前状态 | 上游等价实现/待移植位置 | 差异性质与风险评估 | 处置方案 |
|---|---|---|---|---|---|---|
| 1 | **WebUI 密钥管理** | N/A (本次新需求) | `MessageKeysSection.tsx` 已创建但 Web 正式 build 报错 | `web/src/pages/Config/components/MessageKeysSection.tsx` | **阻断**: `Button.variant`、`ConfirmDialog.variant` 不匹配，未用变量 `t` | 适配 `@nous-research/ui` 正确属性 (`tone="secondary"`、`destructive={true}`)，清理未用变量 |
| 2 | **Desktop 密钥管理** | N/A (本次新需求) | `message-keys-setting.tsx` 已创建但 tsc 报错 | `apps/desktop/src/app/settings/message-keys-setting.tsx` | **阻断**: `notify/notifyError` 传参类型错误、`ListRow` 属性 `subtitle` 应为 `description`，`ConfirmDialog.variant` 不存在 | 修正传参为 `NotificationInput` 对象，更新属性为 `description` 和 `destructive` |
| 3 | **Web/Desktop 汉化** | `web/src/i18n/pagesZh.ts`, `zh.ts`, `messaging-field-localization.ts` | 仅保留基线 `zh.ts`，未触碰 `pagesZh.ts`，新增设置组件硬编码英文 | `web/src/i18n/` 及 `apps/desktop/src/i18n/` | **阻断**: 界面无法按 Fork 标准呈现简体中文，新组件缺 i18n key | 移植 `pagesZh.ts`/`pagesEn.ts` 体系，为 Message Keys 补充中英文词条 |
| 4 | **Gemini OAuth & 反代** | `agent/google_oauth.py`, `agent/gemini_endpoints.py`, `agent/google_code_assist.py`, `agent/gemini_cloudcode_adapter.py` | 完全缺失 (未触碰) | 待移植至 `agent/` 新模块结构，并在 `hermes_cli/auth.py` 和 `model_setup_flows.py` 恢复挂载 | **阻断**: 上游重构仅支持原生 API key，丢失 Google OAuth PKCE 与反代能力 | 完整移植 4 个模块及测试，打通 provider 解析链与登录交互 |
| 5 | **节点间消息工具接入** | `tools/hermes_message_tool.py`, `toolsets.py` | 工具文件已移植，但 `toolsets.py` 未注册 `send_hermes_message` | `toolsets.py` 中的 `_HERMES_CORE_TOOLS` 与 `hermes-api-server` bundle | **阻断**: Agent 无法通过 `api_server` 发现并调用 `send_hermes_message` | 在 `toolsets.py` 注册 `peer_messaging` 并将工具纳入 `hermes-api-server` |
| 6 | **QQBot 文件/图片/审批** | `gateway/platforms/qqbot/adapter.py`, `tools/url_safety.py` | 候选分支使用的是 upstream 原版适配器，缺失 fork 补丁 | `gateway/platforms/qqbot/adapter.py`, `tools/url_safety.py` | **阻断**: QQ 机器人文件/图片检查失效、exec 审批按钮丢失、内网 fake-IP DNS 拦截报错 | 移植 QQBot 增强代码与测试，验证 approval buttons 与图片检查 |
| 7 | **Windows 行为与元数据** | `tests/tools/test_windows_native_support.py`, `hermes_cli/update_cmd_deps.py` | 部分存在，部分待同步 | `tests/tools/test_windows_native_support.py`, `hermes_cli/update_cmd_deps.py` | 兼容性：可编辑安装元数据刷新与 Windows 本地 PTY/命令行为一致性 | 移植 `update_cmd_deps.py` 与对应测试 |

---

## 3. 详细代码改动追踪

### 3.1 Google Gemini CLI OAuth 与反代链路
- `agent/gemini_endpoints.py`: 提供 `normalize_code_assist_base_url`、敏感 URL 抹除 `code_assist_sensitive_values`、及 profile-scoped endpoint 解析。
- `agent/google_oauth.py`: PKCE S256 授权码交换、跨进程文件锁 `_credentials_lock`、本地 callback server 监听与无头环境 paste-mode 备用链路、带自动重试的 access token 刷新。
- `agent/google_code_assist.py`: 负责与 `cloudcode-pa.googleapis.com` 或反代交互，涵盖用户 project context 解析、onboard 引导、配额查询 `/gquota`。
- `agent/gemini_cloudcode_adapter.py`: OpenAI-compatible facade，将 OpenAI 请求翻译为 Gemini CloudCode 格式，并处理 SSE 流式事件。
- `hermes_cli/auth.py` & `hermes_cli/model_setup_flows.py`: 注册 `google-gemini-cli` 登录交互流程及模型配置向导。

### 3.2 QQBot 平台核心增强
- `adapter.py` 文件与多媒体提取：解析 `file_info`、图片消息下载与本地临时缓存、多媒体消息分片上传 (`chunked_upload.py`)。
- 原生审批按钮：通过 QQ 开放平台按钮模板（Markdown 消息附加按钮）实现交互式执行批准（`approve`/`reject`）。
- DNS 防劫持与 Fake-IP 绕过：在 `tools/url_safety.py` 中放行合法的官方 API 与特定解析。

### 3.3 中文 WebUI
- `web/src/i18n/pagesZh.ts` 与 `pagesEn.ts`: 为 WebUI 20+ 个页面提供完整的细粒度文本映射字典。
- `web/src/lib/messaging-field-localization.ts`: 针对各平台特有配置项的中文提示语映射。
- `MessageKeysSection.tsx`: 提取所有 UI 文本至 i18n 资源，支持中文与英文无缝切换。

### 3.4 `send_hermes_message` 工具发现与接入
- `toolsets.py`: 依据 AGENTS.md Footprint Ladder 原则，将 `send_hermes_message` 声明在 `peer_messaging` 工具集，并在 `hermes-api-server` bundle 中默认包含，使 API Server 会话具备节点间路由能力。
