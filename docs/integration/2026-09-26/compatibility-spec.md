# 2026-09-26 Fork 定制能力完整兼容性设计规格 (Specification)

## 1. 目标与设计原则

本规格旨在确保上游同步过程中，Fork 维护的个性化功能在不破坏 upstream 架构规范的前提下 100% 完整保全。

- **原则 1：遵守 Footprint Ladder 与 narrow waist**
  - 不在核心 agent 循环无故增加常驻开销；
  - 节点消息 `send_hermes_message` 通过命名的 `peer_messaging` 工具集和 `hermes-api-server` bundle 接入，不污染轻量 CLI 默认会话。
- **原则 2：严格契约对齐与强类型校验**
  - Web 与 Desktop 前端组件严格匹配各自 UI 库的实际属性契约，严禁 Vitest mock 掩盖编译期类型错误。
- **原则 3：全链路本地化 (i18n)**
  - 任何新增 UI 界面必须配备完整的中英文多语言词条，严禁硬编码英文字符串。
- **原则 4：真实 Provider 链路与安全凭据管理**
  - Google OAuth 凭据遵循 0o600 文件安全模式与跨进程排他锁；
  - 私有反代 Endpoint 需经严格清洗，错误日志中绝不泄露反代私有路径。

---

## 2. 界面与前端规格修正 (Web & Desktop)

### 2.1 WebUI `MessageKeysSection.tsx`
- **组件库规范**：使用 `@nous-research/ui`
  - `Button`：不使用 `variant`。主按钮使用默认，次要操作使用 `tone="secondary"`，危险操作使用 `tone="destructive"` 或 `variant` 以外的规范属性。
  - `ConfirmDialog`：不使用 `variant="destructive"`，使用 `destructive={true}`。
  - `useI18n`：所有界面文本（标题、说明、状态、提示、按钮标签）全部抽取至 `t.messageKeys.*`。
- **状态流转与安全性**：
  - 创建密钥后，明文 Key 仅存于单个瞬时 state 中；
  - 用户复制并关闭通知后，明文被立即丢弃，绝不写入任何 localStorage 或长期 store。

### 2.2 Desktop `message-keys-setting.tsx`
- **契约与 API 修复**：
  - `notify(input)` 与 `notifyError(input)`：参数类型为 `NotificationInput`（例如 `{ title: "..." }` 或带有必须的属性），遵循 `apps/desktop/src/store/notifications.ts` 定义。
  - `ListRow`：辅助文本属性名为 `description`，而非 `subtitle`。
  - `ConfirmDialog`：属性为 `destructive?: boolean`，而非 `variant="destructive"`。
- **本地化与文案**：
  - 接入 Desktop i18n 字典，支持中文/英文双语切换。

---

## 3. Google Gemini CLI OAuth 与反代规格

### 3.1 模块职责与边界
- `agent/gemini_endpoints.py`:
  - 校验并规范化 `code_assist_base_url`、`oauth_authorize_url`、`oauth_token_url`、`oauth_userinfo_url`；
  - `code_assist_sensitive_values`：从 HTTP 报错和日志中脱敏消除反代路径。
- `agent/google_oauth.py`:
  - 遵循 OAuth 2.0 PKCE (RFC 7636) 规范，使用 S256 算法生成 `code_challenge`；
  - 凭据存储于 `get_hermes_home() / "auth" / "google_oauth.json"`，加文件排他锁与 0o600 权限保护；
  - 支持 Headless 无图形终端下的终端直接贴码登录。
- `agent/google_code_assist.py`:
  - 自动向 Google Code Assist API 注册用户或发现已有关联项目；
  - 提供 `/gquota` 配额查询服务。
- `agent/gemini_cloudcode_adapter.py`:
  - 承担 OpenAI 协议至 Gemini CloudCode 协议的转换，支持文本与 Tool Calls 流式响应。

### 3.2 CLI 接入与 Provider 注册
- `hermes_cli/model_setup_flows.py` & `hermes_cli/auth.py`：
  - 注册 `google-gemini-cli` 提供商向导；
  - 用户配置可选的自定义反代 Base URL。

---

## 4. `send_hermes_message` 工具注册规格

- **定位**：Hermes 节点间专有通信工具，需在配置对端（peer）或显式指定 URL 时激活。
- **注册位置**：
  1. `toolsets.py`:
     - 在 `_HERMES_CORE_TOOLS` 中声明 `"send_hermes_message"`；
     - 声明独立工具集 `peer_messaging`，定义其包含 `["send_hermes_message"]`；
     - 在 `hermes-api-server` 工具集 bundle 中默认包含 `"send_hermes_message"`，使得通过 HTTP 运行的 API Server 具备多节点调度能力。

---

## 5. QQBot 平台定制功能保全规格

- **多媒体与文件支持**：
  - 自动拦截接收到的 QQ 文件/图片消息，下载至临时目录并将其注入 Agent 提示词上下文，允许进行多模态或文本审阅。
- **原生执行审批按钮**：
  - 当 Agent 产生危险命令待审批事件时，构造带有确认按钮的 Markdown 消息，用户在 QQ 客户端内可点击直接审批。
- **Fake-IP / 内网安全穿透**：
  - 在 `tools/url_safety.py` 中避免误将本地 fake-ip 识别为恶意内网地址而导致官方接口握手失败。

---

## 6. 验收门槛 (GO/NO-GO Criteria)

1. **构建门槛**：`node scripts/build/web.mjs` 退出码必须为 0，零 TypeScript 编译错误。
2. **类型门槛**：`npx tsc -p apps/desktop/tsconfig.json --noEmit` 零新增错误。
3. **单元与集成测试门槛**：
   - 目标 Python 测试（包含 Gemini、QQBot、Message API、Tool 等）100% 通过。
   - Web 与 Desktop 的 Vitest 测试 100% 通过。
4. **功能完整性门槛**：
   - Web/Desktop 密钥管理界面具备中英双语；
   - `send_hermes_message` 可在 API Server 工具集中被有效发现；
   - Gemini OAuth 与反代模块具备全套单元测试保护。
