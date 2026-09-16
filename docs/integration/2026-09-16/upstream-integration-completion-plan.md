# Hermes 上游兼容候选收尾实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 审核并固化当前上游兼容修复，完成最终回归、提交和可部署候选交付。

**架构：** 保留上游模块边界，以小型兼容适配连接本地认证、API Server、模型配置和 QQBot 行为。现有测试作为行为契约；只修复已确认的接口差异，不新增核心工具或扩展基础设施。

**技术栈：** Python 3.11、pytest、aiohttp、YAML 配置、Git、Windows PowerShell。

---

## 文件职责

- `agent/credential_pool.py`：把显式清除状态传递到认证持久化层。
- `hermes_cli/auth.py`：认证兼容导出、凭据池落盘和 provider 配置保存。
- `hermes_cli/models.py`：模型目录 helper 的稳定导入面。
- `hermes_cli/main.py`、`hermes_cli/main_provider_setup.py`、`hermes_cli/model_setup_flows.py`：交互式 provider/model 配置接口。
- `gateway/run.py`：Gateway 类型和运行时 provider 接口兼容。
- `gateway/platforms/api_server.py`：API Server 初始化、agent 创建、能力声明及 message 配置。
- `gateway/platforms/api_server_openai_routes.py`：OpenAI 请求、session、relay metadata 和运行参数传递。
- `gateway/platforms/api_server_runs.py`：run 状态及 continuation session ID 解析。
- `gateway/platforms/qqbot/adapter.py`：QQBot 会话、附件和授权兼容。
- `tests/...`：上述行为的现有回归契约；仅在发现未覆盖的真实行为时增加最小测试。

### 任务 1：锁定最终差异范围

- [ ] **步骤 1：确认正确工作区和分支**

```powershell
Set-Location 'F:\Documents\Project\hermes-agent\.worktrees\upstream-20260914'
git branch --show-current
git rev-parse HEAD
git status --short
```

预期：分支为 `integration/upstream-20260914`；开始时 HEAD 可为 `e144ed8cdc`；保留所有现有修改。

- [ ] **步骤 2：检查本次生产差异**

```powershell
git diff -- agent/credential_pool.py gateway/platforms/api_server.py gateway/platforms/api_server_openai_routes.py gateway/platforms/api_server_runs.py gateway/platforms/qqbot/adapter.py gateway/run.py hermes_cli/auth.py hermes_cli/main.py hermes_cli/main_provider_setup.py hermes_cli/model_setup_flows.py hermes_cli/models.py
git diff --check
```

预期：无冲突标记、尾随空格或空实现；每项差异对应规格 R1-R7。

- [ ] **步骤 3：核对关键接口没有重复实现**

```powershell
rg -n "def _create_agent|def _resolve_provider_runtime|def _idempotency_capabilities|def _resolve_live_session_id|def write_credential_pool|def _update_config_for_provider" agent gateway hermes_cli
```

预期：每个职责只有一个实际入口；API Server 构造函数完整结束后才定义类方法。

### 任务 2：验证基础兼容契约

- [ ] **步骤 1：运行 API Server 与 provider 测试**

```powershell
python -m pytest tests/gateway/test_api_server.py tests/hermes_cli/test_runtime_provider_resolution.py tests/hermes_cli/test_model_provider_persistence.py -q --tb=short
```

预期：`212 passed`，退出码 0。

- [ ] **步骤 2：失败时只修复共享根因**

处理规则：

- session continuation resolver 只接受 `isinstance(resolved, str)` 且 `resolved.strip()` 非空的返回值。
- provider 配置保存仅在 `model.default` 为空或用户明确选择新模型时写入默认模型。
- API Server 初始化字段必须位于 `APIServerAdapter.__init__` 内，不在方法返回之后补默认值。
- provider/runtime 参数必须通过已有 resolver 和 `_create_agent()` 签名传递。

- [ ] **步骤 3：修复后重跑同一命令**

预期：`212 passed`，退出码 0；记录 warning 数量，不把 warning 当作通过项隐藏。

### 任务 3：验证本地个性化兼容契约

- [ ] **步骤 1：运行认证、QQBot、Gemini 与 message 回归**

```powershell
python -m pytest tests/agent/test_credential_pool.py tests/gateway/test_qqbot.py tests/agent/test_gemini_endpoints.py tests/tools/test_hermes_message_tool.py -q --tb=short
```

预期：`248 passed`，退出码 0。

- [ ] **步骤 2：检查安全和异步 warning**

若出现 `RuntimeWarning: coroutine was never awaited`、SSRF 测试失败、授权绕过或密钥泄漏 warning，必须修复对应共享路径后重跑任务 2 和任务 3。

### 任务 4：执行代码级审查

- [ ] **步骤 1：检查认证与模型配置不变量**

确认 OAuth grant 导出来自 `auth_oauth_grants`，`status_cleared_ids` 贯穿持久化链，provider 保存不覆盖既有默认模型，ZAI endpoint 使用现有 prompt helper。

- [ ] **步骤 2：检查 API Server 不变量**

确认构造函数初始化完整、continuation 只接受真实字符串、`_create_agent()` 与 routes 参数一致、`runs_idempotency` 为结构化对象。

- [ ] **步骤 3：检查 QQBot 不变量**

确认命名 profile 会话键、DM 授权、附件下载安全和协程关闭逻辑均由现有测试覆盖；不扩大文件读取信任边界。

### 任务 5：静态验证与最终提交

- [ ] **步骤 1：运行编译检查**

```powershell
python -m compileall -q agent gateway hermes_cli tools
```

预期：退出码 0。

- [ ] **步骤 2：暂存精确文件**

```powershell
git add agent/credential_pool.py gateway/platforms/api_server.py gateway/platforms/api_server_openai_routes.py gateway/platforms/api_server_runs.py gateway/platforms/qqbot/adapter.py gateway/run.py hermes_cli/auth.py hermes_cli/main.py hermes_cli/main_provider_setup.py hermes_cli/model_setup_flows.py hermes_cli/models.py docs/integration/2026-09-16/compatibility-completion-spec.md docs/integration/2026-09-16/upstream-integration-completion-plan.md docs/integration/2026-09-14/zcode-next-task.md
git diff --cached --check
git diff --cached --stat
```

预期：只包含列出的兼容代码和权威文档；不暂存其他历史未跟踪文件。

- [ ] **步骤 3：提交候选**

```powershell
git commit -m "fix(integration): complete upstream compatibility candidate"
git rev-parse HEAD
git status --short
```

预期：生成新的提交 SHA；生产文件无未提交修改。

### 任务 6：提交后复验和报告

- [ ] **步骤 1：在提交后重跑两组规定测试**

```powershell
python -m pytest tests/gateway/test_api_server.py tests/hermes_cli/test_runtime_provider_resolution.py tests/hermes_cli/test_model_provider_persistence.py -q --tb=short
python -m pytest tests/agent/test_credential_pool.py tests/gateway/test_qqbot.py tests/agent/test_gemini_endpoints.py tests/tools/test_hermes_message_tool.py -q --tb=short
```

预期：分别 `212 passed`、`248 passed`。

- [ ] **步骤 2：验证提交内容**

```powershell
git diff --check HEAD^ HEAD
git show --stat --oneline HEAD
git status --short --branch
```

预期：提交差异检查通过；只剩明确保留的历史未跟踪文档。

- [ ] **步骤 3：输出交付报告**

报告必须包含提交 SHA、两组测试通过数量、warning 数量、编译检查结果、未跟踪文件清单，以及尚未执行本地部署和远程部署的事实状态。
