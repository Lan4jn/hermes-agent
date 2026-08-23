# Antigravity 核心后端与经典 CLI 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 交付可通过 `hermes model` 安装、登录和配置的 Antigravity Headless 后端，并让经典 Hermes CLI 能按会话在 Hermes 与 Antigravity 之间切换。

**架构：** 新建 `agent/backends` 边缘包，使用官方 `agy` stdin/stdout NDJSON 协议维护长期会话；原生 Hermes 路径不改写，只在会话明确解析为 Antigravity 时旁路 `AIAgent.run_conversation()`。SessionDB 保存后端选择和 Antigravity conversation ID，配置和安装向导复用现有 YAML/.env 原子写入能力。

**技术栈：** Python 3.11、stdlib `subprocess`/`threading`/`queue`、ruamel/PyYAML、SQLite、pytest。

---

## 文件结构

- 创建：`agent/backends/__init__.py`，公开稳定后端类型。
- 创建：`agent/backends/base.py`，定义 turn/event/result 契约。
- 创建：`agent/backends/hermes.py`，包装表面注入的原生 Hermes turn callable。
- 创建：`agent/backends/config.py`，解析后端、权限和正向代理配置。
- 创建：`agent/backends/antigravity.py`，实现单个长期 `agy` 会话。
- 创建：`agent/backends/pool.py`，实现跨会话池、LRU 和关闭。
- 创建：`agent/backends/router.py`，解析全局/平台/会话后端并持久化覆盖。
- 创建：`agent/backends/setup.py`，实现检测、安装、登录、模型和代理向导。
- 创建：`tests/fixtures/fake_agy.py`，提供真实 NDJSON 子进程测试替身。
- 创建：`tests/agent/backends/test_antigravity.py`，覆盖协议、进程和安全。
- 创建：`tests/agent/backends/test_pool.py`，覆盖并发、回收和恢复。
- 创建：`tests/agent/backends/test_router.py`，覆盖配置优先级和持久化。
- 创建：`tests/hermes_cli/test_antigravity_setup.py`，覆盖安装和 `hermes model`。
- 修改：`hermes_state_common.py`、`hermes_state_schema.py`、`hermes_state.py`，保存后端元数据。
- 修改：`hermes_cli/config_defaults.py`，声明配置默认值。
- 修改：`hermes_cli/models.py`、`hermes_cli/main.py`，增加 Google/Antigravity 向导入口。
- 修改：`hermes_cli/subcommands/gateway.py`、`hermes_cli/gateway.py`，增加 host-side setup/status。
- 修改：`hermes_cli/commands.py`、`cli.py`，增加 `/backend` 和经典 CLI 路由。

### 任务 1：配置与后端契约

**文件：**
- 创建：`agent/backends/__init__.py`
- 创建：`agent/backends/base.py`
- 创建：`agent/backends/hermes.py`
- 创建：`agent/backends/config.py`
- 修改：`hermes_cli/config_defaults.py`
- 测试：`tests/agent/backends/test_router.py`

- [ ] **步骤 1：先写失败测试**

测试必须断言：默认解析为 `hermes`；session > platform > global > built-in；权限只接受 `strict|sandbox|trusted`；代理拒绝 userinfo/query/fragment/非 HTTP(S)；`${ANTIGRAVITY_PROXY_URL}` 展开后的凭据 URL只在内存中存在。

```python
def test_backend_resolution_order():
    cfg = {
        "agent_backends": {"default": "antigravity"},
        "platforms": {"telegram": {"extra": {"agent_backend": "hermes"}}},
    }
    assert resolve_backend(cfg, platform="telegram", session_override="antigravity").name == "antigravity"
    assert resolve_backend(cfg, platform="telegram").name == "hermes"
    assert resolve_backend(cfg, platform="qqbot").name == "antigravity"
    assert resolve_backend({}, platform="cli").name == "hermes"
```

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/agent/backends/test_router.py -q`

预期：FAIL，`agent.backends` 尚不存在。

- [ ] **步骤 3：实现最小契约和解析器**

`BackendTurnRequest` 包含 `session_id/profile/platform/principal_id/text/cwd/media_paths/trusted`；`BackendTurnResult` 包含 `response/conversation_id/usage/status`；事件类型只定义 `message_delta/tool/status` 三类事实，不复制 UI 渲染逻辑。`HermesBackend` 接收表面提供的 native turn callable，原样调用并返回结果，使 router 有真实 Hermes consumer 而不搬迁现有 agent loop。

配置解析返回不可变 `AntigravityConfig`，代理校验使用 `urllib.parse.urlsplit`，并为日志提供不含 userinfo 的 `proxy_display`。

- [ ] **步骤 4：运行绿灯和配置回归**

运行：`python -m pytest tests/agent/backends/test_router.py tests/hermes_cli/test_config.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/backends hermes_cli/config_defaults.py tests/agent/backends/test_router.py
git commit -m "feat: define interactive agent backend config"
```

### 任务 2：真实 NDJSON Antigravity 会话

**文件：**
- 创建：`agent/backends/antigravity.py`
- 创建：`tests/fixtures/fake_agy.py`
- 创建：`tests/agent/backends/test_antigravity.py`

- [ ] **步骤 1：写协议失败测试**

Fake `agy` 必须读取多条 `user` 行，首次发 `init`，每轮发 `agent_response` ACTIVE/DONE、可选 tool step 和一个 `result`。测试真实启动子进程，断言两个 turn 复用同一 PID/conversation ID、delta 顺序正确、usage 可读取。

```python
result = session.run_turn(request("first"), events.append)
second = session.run_turn(request("second"), events.append)
assert result.conversation_id == second.conversation_id == "fake-conversation"
assert [event.text for event in events if event.kind == "message_delta"] == ["first", "second"]
```

补充参数化测试：`strict` 无额外 flag，`sandbox` 带 `--sandbox`，只有 `request.trusted=True` 的 `trusted` 才带 `--dangerously-skip-permissions`；未授权 trusted 在 spawn 前失败。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/agent/backends/test_antigravity.py -q`

预期：FAIL，`AntigravitySession` 尚不存在。

- [ ] **步骤 3：实现进程和协议**

使用参数数组启动：`agy --input-format stream-json --output-format stream-json --model MODEL --effort EFFORT`。stdin/stdout 使用 UTF-8 行缓冲；stdout reader 解析 JSON 入队；stderr reader 写入 `deque(maxlen=40)` 并应用现有 secret redaction。Windows使用 `windows_hide_flags()`。

每次 turn 等待同轮 `result`；未知 event 忽略并 debug 记录；超长行、非法 JSON、非 SUCCESS状态和提前退出抛出带有 bounded stderr 的 `AntigravityBackendError`。关闭顺序是 close stdin -> wait -> terminate -> kill。

- [ ] **步骤 4：验证绿灯**

运行：`python -m pytest tests/agent/backends/test_antigravity.py -q`

预期：PASS，进程测试结束后无 fake `agy` 残留。

- [ ] **步骤 5：提交**

```bash
git add agent/backends/antigravity.py tests/fixtures/fake_agy.py tests/agent/backends/test_antigravity.py
git commit -m "feat: add Antigravity headless transport"
```

### 任务 3：会话池、容量和恢复

**文件：**
- 创建：`agent/backends/pool.py`
- 测试：`tests/agent/backends/test_pool.py`

- [ ] **步骤 1：写失败测试**

覆盖 profile/platform/session 复合键、每会话串行锁、不同会话并发、只驱逐 idle LRU、全 busy 时拒绝、idle timeout、shutdown、崩溃后携带 `--conversation` 恢复一次。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/agent/backends/test_pool.py -q`

预期：FAIL，pool 尚不存在。

- [ ] **步骤 3：实现最小池**

使用一个锁保护字典和 LRU 时间戳，不引入新依赖。`run_turn()` 在容量检查后取得 session 专属锁；busy entry 不参与驱逐；恢复仅一次，第二次失败原样返回。

- [ ] **步骤 4：运行绿灯**

运行：`python -m pytest tests/agent/backends/test_pool.py tests/agent/backends/test_antigravity.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/backends/pool.py tests/agent/backends/test_pool.py
git commit -m "feat: manage Antigravity backend sessions"
```

### 任务 4：SessionDB 后端状态

**文件：**
- 修改：`hermes_state_common.py`
- 修改：`hermes_state_schema.py`
- 修改：`hermes_state.py`
- 测试：`tests/test_hermes_state.py`

- [ ] **步骤 1：写 schema 失败测试**

创建旧 schema 临时 DB 后打开新版 SessionDB，断言自动增加 `agent_backend TEXT NOT NULL DEFAULT ''` 和 `backend_conversation_id TEXT NOT NULL DEFAULT ''`；现有消息和模型字段不变。再测试 set/get 清空方法和不存在 session 的失败结果。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/test_hermes_state.py -k agent_backend -q`

预期：FAIL，列和方法不存在。

- [ ] **步骤 3：实现向后兼容字段和方法**

在 `SCHEMA_SQL` sessions 表声明两列，由现有 `_reconcile_columns()` 自动补列；添加 `set_session_agent_backend(session_id, backend, conversation_id="")`，使用 SessionDB 写锁和单次 UPDATE。所有 session row 解码路径自然返回两字段。

- [ ] **步骤 4：运行 schema 回归**

运行：`python -m pytest tests/test_hermes_state.py tests/test_hermes_state_readonly_preflight.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add hermes_state_common.py hermes_state_schema.py hermes_state.py tests/test_hermes_state.py
git commit -m "feat: persist interactive backend session state"
```

### 任务 5：安装、登录、模型和代理向导

**文件：**
- 创建：`agent/backends/setup.py`
- 修改：`hermes_cli/subcommands/gateway.py`
- 修改：`hermes_cli/gateway.py`
- 创建：`tests/hermes_cli/test_antigravity_setup.py`

- [ ] **步骤 1：写失败测试**

测试 Windows/POSIX 检测顺序；安装必须显式确认；取消、下载失败、`agy --version` 失败、`agy models` 未登录/空列表均不写配置；代理 URL校验；认证代理写 `.env` 的 `ANTIGRAVITY_PROXY_URL` 和 `${ANTIGRAVITY_PROXY_URL}` 引用；stderr 不含凭据。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/hermes_cli/test_antigravity_setup.py -q`

预期：FAIL，setup API不存在。

- [ ] **步骤 3：实现交互式 setup/status**

扩展 parser 支持：

```text
hermes gateway backend setup antigravity
hermes gateway backend status antigravity
```

安装器先下载到临时文件再执行，不拼接用户输入；proxy 只放在 installer/`agy` 子进程 env。模型列表从 `agy models` stdout 解析，选择并确认后用 `atomic_roundtrip_yaml_save` 写原始用户配置。

- [ ] **步骤 4：运行绿灯**

运行：`python -m pytest tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_subcommands_batch.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/backends/setup.py hermes_cli/subcommands/gateway.py hermes_cli/gateway.py tests/hermes_cli/test_antigravity_setup.py
git commit -m "feat: configure Antigravity gateway backend"
```

### 任务 6：`hermes model` Google 入口

**文件：**
- 修改：`hermes_cli/models.py`
- 修改：`hermes_cli/main.py`
- 修改：`hermes_cli/model_setup_flows.py`
- 修改：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：写失败测试**

断言 Google 子菜单含 `Google Antigravity CLI (AI Pro)`；选择后调用同一 setup flow；成功只写 `agent_backends`/platform overrides，不改变 `model.default/provider/base_url`、API keys、fallback 或 auxiliary；取消零写入。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -k antigravity -q`

预期：FAIL，picker 没有 Antigravity。

- [ ] **步骤 3：接入专用叶子**

将 `antigravity-cli` 作为 Google 分组的 setup-only成员，dispatch 到 `_model_flow_antigravity()`；该 flow 只调用 setup模块并打印“native Hermes model preserved”。不得进入 provider credential cleanup 或写 `model.provider`。

- [ ] **步骤 4：运行模型设置回归**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py tests/hermes_cli/test_gemini_provider.py tests/hermes_cli/test_commands.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add hermes_cli/models.py hermes_cli/main.py hermes_cli/model_setup_flows.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "feat: expose Antigravity in model setup"
```

### 任务 7：共享 router 与经典 CLI 消费者

**文件：**
- 创建：`agent/backends/router.py`
- 修改：`hermes_cli/commands.py`
- 修改：`cli.py`
- 创建：`tests/cli/test_antigravity_backend.py`

- [ ] **步骤 1：写失败 E2E**

以 fake `agy` 启动真实 `HermesCLI` turn 边界：Antigravity 会话不调用 `AIAgent.run_conversation`；Hermes 会话仍只调用原路径；delta 进入现有 stream callback；最终 user/assistant transcript 落库；`/backend` 查询和切换持久化；`/new` 继承默认而非旧 override。

- [ ] **步骤 2：运行红灯**

运行：`python -m pytest tests/cli/test_antigravity_backend.py -q`

预期：FAIL，CLI 尚未路由。

- [ ] **步骤 3：最小接入经典 CLI**

在现有 `self.agent.run_conversation()` 调用点前解析 backend。Hermes 分支保留原代码字节结构；Antigravity 分支构造 `BackendTurnRequest`、复用现有 stream callback、保存 transcript，并返回与现有 result dict兼容的结果。退出和 interrupt 调用 router cleanup。

`COMMAND_REGISTRY` 增加 `backend`，handler 只接受空参数、`hermes`、`antigravity`。

- [ ] **步骤 4：运行绿灯与 CLI 回归**

运行：`python -m pytest tests/cli/test_antigravity_backend.py tests/cli/test_cli_retry.py tests/hermes_cli/test_commands.py -q`

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/backends/router.py hermes_cli/commands.py cli.py tests/cli/test_antigravity_backend.py
git commit -m "feat: route classic CLI to Antigravity"
```

### 任务 8：阶段 1 验证

- [ ] **步骤 1：运行全阶段测试**

运行：`python -m pytest tests/agent/backends tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/cli/test_antigravity_backend.py tests/test_hermes_state.py -q`

预期：全部 PASS。

- [ ] **步骤 2：运行静态和差异检查**

运行：`python -m compileall -q agent/backends hermes_cli cli.py hermes_state.py && git diff --check`

预期：退出码 0。

- [ ] **步骤 3：真实 smoke test**

在 Windows 安装/登录 `agy`，运行 `hermes model` 选择 Antigravity，发送两轮 CLI 消息，执行 `/backend hermes` 后再发一轮；确认 PID复用、会话 ID保存、切回 Hermes 正常。130 的真实安装部署留到阶段 2 全表面验证。
