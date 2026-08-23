# Antigravity 全交互界面接入实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**前置条件：** 完成 `docs/superpowers/plans/2026-08-23-antigravity-core-cli.md`，其核心后端、router、SessionDB字段和经典 CLI E2E 全部通过。

**目标：** 将已验证的 Antigravity 后端接入 TUI、桌面、Dashboard、消息网关和 `/message`，同时落实可信用户权限边界，并证明 Cron/批处理仍固定使用 Hermes。

**架构：** 所有表面只构造共享 `BackendTurnRequest` 并消费共享 backend events；不复制 `agy` 进程协议。Hermes 分支继续调用现有 `AIAgent.run_conversation()`，Antigravity 分支旁路 core agent，将 tool/message事件映射到各表面已有事件和交付系统。

**技术栈：** Python asyncio/thread executor、现有 TUI JSON-RPC、gateway stream events、React/TypeScript desktop command curation、pytest/vitest。

---

## 文件结构

- 创建：`tui_gateway/interactive_backend.py`，桥接 shared router 与 TUI事件。
- 修改：`tui_gateway/server.py`、`tui_gateway/compute_host.py`，在 prompt边界选择 backend。
- 修改：`apps/desktop/src/lib/desktop-slash-commands.ts` 及测试，公开 `/backend`。
- 创建：`gateway/interactive_backend.py`，桥接 shared router 与 gateway delivery events。
- 修改：`gateway/run.py`、`gateway/slash_commands.py`、`gateway/session.py`，路由普通消息和会话生命周期。
- 修改：`gateway/platforms/api_server.py`，在 `/message` spawn 前执行 API key gate。
- 修改：`gateway/platforms/base.py` 或现有媒体 helper，构造安全文件引用。
- 创建：`tests/tui_gateway/test_antigravity_backend.py`。
- 创建：`tests/gateway/test_antigravity_backend.py`。
- 创建：`tests/gateway/test_antigravity_message_auth.py`。
- 修改：`apps/desktop/src/lib/desktop-slash-commands.test.ts`。

### 任务 1：TUI Gateway turn 路由

**文件：**
- 创建：`tui_gateway/interactive_backend.py`
- 修改：`tui_gateway/server.py`
- 修改：`tui_gateway/compute_host.py`
- 创建：`tests/tui_gateway/test_antigravity_backend.py`

- [ ] **步骤 1：写失败 E2E**

使用 fake `agy` 和真实 `prompt.submit` handler，断言 `message.delta`、`tool.start/complete`、`message.complete` 顺序；SessionDB保存 backend/conversation ID；`session.interrupt` 中断 child；Hermes backend 原路径不变；`/new` 清理旧 child。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/tui_gateway/test_antigravity_backend.py -q`

预期：FAIL，TUI仍只调用 agent。

- [ ] **步骤 3：实现事件桥**

`run_interactive_backend_turn(session, run_message, emit)` 先解析 backend。Hermes返回 sentinel 让 caller执行现有代码；Antigravity通过 `_run_in_executor_with_context` 调用共享 router，将 message/tool/status映射到现有 `_emit`。最终组装兼容 result dict并复用当前 transcript/usage completion代码。

只修改主交互 prompt路径；synthetic turns、标题、compression、auxiliary和 compute-only jobs继续 Hermes。`compute_host` 只在它代表用户交互会话时调用桥，否则不变。

- [ ] **步骤 4：运行绿灯与 TUI 回归**

运行：`python -m pytest tests/tui_gateway/test_antigravity_backend.py tests/tui_gateway/test_prompt_accept_logging.py tests/test_tui_gateway_server.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add tui_gateway/interactive_backend.py tui_gateway/server.py tui_gateway/compute_host.py tests/tui_gateway/test_antigravity_backend.py
git commit -m "feat: route TUI sessions to Antigravity"
```

### 任务 2：Desktop 与 Dashboard 命令发现

**文件：**
- 修改：`apps/desktop/src/lib/desktop-slash-commands.ts`
- 修改：`apps/desktop/src/lib/desktop-slash-commands.test.ts`
- 修改：`apps/shared/src/json-rpc-gateway.ts`（仅当 backend 状态需要新增 typed event）

- [ ] **步骤 1：写失败测试**

断言 `/backend` 出现在 desktop catalog、可执行且参数模式允许一个文本参数；它不被 terminal-only blocklist过滤。现有 extension command通过规则保持不变。

- [ ] **步骤 2：运行红灯**

运行：`npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts`

预期：FAIL，backend 未列入 desktop spec。

- [ ] **步骤 3：最小更新 command curation**

加入 `backend` command spec，并让现有 `slash.exec`/`command.dispatch`处理；不在 React 重写 picker。Dashboard嵌入真实 TUI，零专用实现。

- [ ] **步骤 4：运行绿灯和类型检查**

运行：`npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts && npm --prefix apps/desktop run type-check`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add apps/desktop/src/lib/desktop-slash-commands.ts apps/desktop/src/lib/desktop-slash-commands.test.ts apps/shared/src/json-rpc-gateway.ts
git commit -m "feat: expose backend switching in desktop"
```

### 任务 3：Gateway 主消息路由与事件映射

**文件：**
- 创建：`gateway/interactive_backend.py`
- 修改：`gateway/run.py`
- 修改：`gateway/session.py`
- 创建：`tests/gateway/test_antigravity_backend.py`

- [ ] **步骤 1：写失败 gateway E2E**

构造 allowlisted QQBot/Telegram source，走真实 gateway foreground消息边界，断言 Antigravity时不构造 AIAgent；message delta进入 `GatewayStreamConsumer`；tool事件只显示 sanitized name/preview；最终 reply走原 adapter delivery和SessionDB。Hermes backend对照测试断言原构造参数和调用次数不变。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py -q`

预期：FAIL，gateway尚未路由。

- [ ] **步骤 3：实现 gateway event bridge**

在平台 authorization、slash command和media staging之后，在 AIAgent构造前解析 backend。Antigravity请求携带 profile/platform/session/principal/cwd/trusted；message delta映射 `MessageChunk`，tool start/finish映射现有 `ToolCallChunk/ToolCallFinished`，final沿用 delivery ledger。

后台任务、Cron通知、handoff worker和 auxiliary call sites不调用 bridge，继续 Hermes。

- [ ] **步骤 4：运行绿灯和 sibling 路径回归**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py tests/gateway/test_turn_lease.py tests/gateway/test_stream_events.py tests/gateway/test_qqbot_attachments.py -q`

预期：PASS；如 attachment测试文件名不同，使用 `rg --files tests/gateway | rg 'qqbot.*(file|attachment|media)'` 选取现有真实套件。

- [ ] **步骤 5：提交**

```bash
git add gateway/interactive_backend.py gateway/run.py gateway/session.py tests/gateway/test_antigravity_backend.py
git commit -m "feat: route gateway chats to Antigravity"
```

### 任务 4：Gateway `/backend` 命令

**文件：**
- 修改：`gateway/slash_commands.py`
- 修改：`gateway/run.py`
- 修改：`tests/hermes_cli/test_commands.py`
- 修改：`tests/gateway/test_antigravity_backend.py`

- [ ] **步骤 1：写失败测试**

覆盖 bare命令显示 effective值和来源；切换只更新当前 session；未知参数不写；未授权用户不能切 Antigravity；`/new` 使用平台/global默认；help/Telegram menu/Slack routing从中央 registry自动出现。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py tests/hermes_cli/test_commands.py -k backend -q`

预期：FAIL，gateway handler尚未实现。

- [ ] **步骤 3：实现 handler**

调用 shared router 的 query/set方法，不复制配置逻辑。切离 Antigravity时关闭当前 child但保留 opaque conversation ID；切回可恢复。响应中明确 `session/platform/global/built-in` 来源。

- [ ] **步骤 4：运行绿灯**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py tests/hermes_cli/test_commands.py tests/gateway/test_telegram_forum_commands.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add gateway/slash_commands.py gateway/run.py tests/hermes_cli/test_commands.py tests/gateway/test_antigravity_backend.py
git commit -m "feat: switch gateway agent backends per session"
```

### 任务 5：`/message` API_SERVER_KEY 安全边界

**文件：**
- 修改：`gateway/platforms/api_server.py`
- 创建：`tests/gateway/test_antigravity_message_auth.py`

- [ ] **步骤 1：写失败安全测试**

配置 `/message` backend=antigravity并分别参数化 `trusted|strict|sandbox`。无 key、错误 bearer、只有普通 message均返回401，且 pool spawn mock为0次；有效 bearer、`X-Hermes-Api-Key`、body api_key、有效 exec_token允许。Hermes backend继续保持现有 message行为。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/gateway/test_antigravity_message_auth.py -q`

预期：FAIL，普通 message会进入 backend。

- [ ] **步骤 3：在 spawn 前加 gate**

复用现有 bearer/body/token比较结果，不复制 key解析。确定 effective backend后，任何 Antigravity turn未授权都立即返回 OpenAI-style gateway auth错误。不得先创建SessionDB child状态或 `agy` 进程。

- [ ] **步骤 4：运行安全回归**

运行：`python -m pytest tests/gateway/test_antigravity_message_auth.py tests/gateway/test_api_server_message.py tests/gateway/test_weak_credential_guard.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add gateway/platforms/api_server.py tests/gateway/test_antigravity_message_auth.py
git commit -m "fix: gate trusted Antigravity message turns"
```

### 任务 6：文件与图片安全引用

**文件：**
- 修改：`gateway/interactive_backend.py`
- 修改：`gateway/platforms/base.py`（仅复用入口不足时）
- 修改：`tests/gateway/test_antigravity_backend.py`

- [ ] **步骤 1：写失败测试**

允许现有 media cache/workspace内的 QQ/Telegram文件；拒绝 credential/system denylist、路径遍历、已删除文件和任意绝对路径。图片不作为 unsupported NDJSON block发送，而生成含安全本地引用的文本。日志不打印被拒绝路径中的敏感片段。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py -k media -q`

预期：FAIL，safe reference构造尚不存在。

- [ ] **步骤 3：复用 media policy**

调用现有 `validate_media_delivery_path`/media-policy helper，不创建第二套路径 allowlist。请求只携带验证通过且存在的 resolved paths；失败项变成固定 unavailable note。

- [ ] **步骤 4：运行绿灯**

运行：`python -m pytest tests/gateway/test_antigravity_backend.py -k media -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add gateway/interactive_backend.py gateway/platforms/base.py tests/gateway/test_antigravity_backend.py
git commit -m "fix: validate Antigravity media references"
```

### 任务 7：Cron、Batch 与 native Hermes 不变量

**文件：**
- 创建：`tests/agent/backends/test_noninteractive_isolation.py`
- 仅在测试证明泄漏时修改：`cron/scheduler.py`、`batch_runner.py`、`agent/auxiliary_client.py`

- [ ] **步骤 1：写不变量测试**

设置 `agent_backends.default=antigravity`，运行 cron agent factory、batch runner和 auxiliary resolver，断言均创建/解析 native Hermes provider且从不访问 backend router/pool。

- [ ] **步骤 2：运行测试**

运行：`python -m pytest tests/agent/backends/test_noninteractive_isolation.py -q`

预期：若现有路径天然隔离则直接 PASS；若失败，失败必须指出具体共享入口。

- [ ] **步骤 3：只修复实际泄漏**

在泄漏入口显式指定 `interactive=False` 或绕开 router，不重构无关 factory。

- [ ] **步骤 4：运行回归**

运行：`python -m pytest tests/agent/backends/test_noninteractive_isolation.py tests/cron tests/test_batch_runner.py -q`

预期：PASS；若 batch测试采用其他文件名，用 `rg --files tests | rg 'batch'` 选取现有套件。

- [ ] **步骤 5：提交**

```bash
git add tests/agent/backends/test_noninteractive_isolation.py cron/scheduler.py batch_runner.py agent/auxiliary_client.py
git commit -m "test: keep unattended work on Hermes backend"
```

### 任务 8：阶段 2 综合验证与部署 smoke

- [ ] **步骤 1：运行 Python 聚焦套件**

运行：`python -m pytest tests/agent/backends tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/hermes_cli/test_antigravity_setup.py -q`

预期：全部 PASS。

- [ ] **步骤 2：运行已有跨表面回归**

运行：`python -m pytest tests/hermes_cli/test_commands.py tests/test_tui_gateway_server.py tests/gateway/test_stream_events.py tests/gateway/test_turn_lease.py tests/test_hermes_state.py -q`

预期：PASS，只有既有明确 SKIP。

- [ ] **步骤 3：运行 Desktop 测试和类型检查**

运行：`npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts && npm --prefix apps/desktop run type-check`

预期：PASS。

- [ ] **步骤 4：静态检查**

运行：`python -m compileall -q agent/backends tui_gateway gateway hermes_cli cli.py && git diff --check`

预期：退出码0。

- [ ] **步骤 5：Windows 与 130 安装验证**

在两台主机分别运行 `hermes gateway backend setup antigravity`，通过正向代理安装/登录，确认 `agy models` 可列出模型。分别测试 CLI、TUI、QQBot、Telegram和`/message`两轮会话；验证同会话conversation ID稳定、不同会话隔离、`/backend hermes`恢复原功能、未认证`/message`返回401、网关重启后恢复会话。

- [ ] **步骤 6：进程清理和版本一致性**

关闭会话和网关后检查无孤儿 `agy`；比较本地与130部署源码哈希；记录回滚备份路径后再报告完成。
