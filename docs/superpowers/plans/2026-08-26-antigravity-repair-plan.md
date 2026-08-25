# Antigravity Backend 修复实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 修复 Antigravity backend 已发现的 setup、配置作用域、会话池、进程生命周期和表面集成问题，使官方 `agy` 能在 CLI、TUI、Desktop、Gateway 和 `/message` 上安全、稳定地多轮运行。

**架构：** 保留现有 `agent/backends` 边缘模块，不新增 provider 或 core tool。所有表面向 `BackendRouter` 提供已经按 profile 解析的 Mapping；每个运行域只拥有一个明确生命周期的 router/pool。setup 只使用 Google 官方 CLI 契约，失败时不写配置、不伪造模型。

**技术栈：** Python 3.11、stdlib subprocess/threading/queue、SQLite、pytest、Vitest、TypeScript。

---

## 执行前置条件

当前 worktree 有 19 个未提交修复文件。执行者必须先与当前修改者确认所有权并保存现状：

```powershell
git status --short
git diff --check
git diff --stat
```

不得 `reset`、`checkout --` 或丢弃这些修改。确认后将当前 WIP 独立提交，或从其提交创建新的修复 worktree。后续每个任务一个提交。

## 根因与修复边界

1. setup 将非官方安装 URL、宽松模型解析和硬编码 fallback 混在一个流程中。
2. Antigravity 是 agent backend，但 `hermes model` 的 provider picker 没有 setup-only action。
3. Gateway/TUI/API 各自猜测配置类型，导致 profile/global 配置在生产对象上丢失。
4. pool 用布尔 `busy` 表达 active + waiter，无法正确处理并发租约和关闭失败。
5. transport 缺少 bounded queue/turn budget、URL credential redaction 和跨表面 interrupt。
6. 媒体路径没有进入 `agy` prompt，backend/session 状态在 resume/new/teardown 时不完整。

不要增加第三套 router、provider facade、HTTP proxy server 或自定义 Google 协议。

### 任务 1：修复官方 setup 契约

**文件：**
- 修改：`agent/backends/setup.py`
- 修改：`agent/backends/config.py`
- 测试：`tests/hermes_cli/test_antigravity_setup.py`

- [ ] **步骤 1：编写失败测试**

增加以下行为测试：

```python
def test_official_installer_urls_are_antigravity_google():
    assert OFFICIAL_INSTALLER_WINDOWS == "https://antigravity.google/cli/install.ps1"
    assert OFFICIAL_INSTALLER_POSIX == "https://antigravity.google/cli/install.sh"

def test_parse_models_uses_slug_not_display_label():
    stdout = "gemini-3.7-flash-high Gemini 3.7 Flash (High)\nclaude-sonnet-4-6 Claude Sonnet 4.6 (Thinking)\n"
    assert parse_antigravity_models(stdout) == [
        "gemini-3.7-flash-high",
        "claude-sonnet-4-6",
    ]

def test_empty_catalog_after_login_performs_no_write(config_home, monkeypatch):
    config_path = config_home / "config.yaml"
    env_path = config_home / ".env"
    before = config_path.read_text(encoding="utf-8")
    env_before = env_path.read_text(encoding="utf-8")
    monkeypatch.setattr(setup, "detect_antigravity_executable", lambda *_: "agy")
    monkeypatch.setattr(setup, "verify_antigravity_executable", lambda *_args, **_kw: "agy 1.0")
    monkeypatch.setattr(setup, "probe_antigravity_models", lambda *_args, **_kw: ([], "authentication required"))
    assert setup.run_antigravity_setup(interactive=False, custom_config={}) is False
    assert config_path.read_text() == before
    assert env_path.read_text() == env_before
```

同时覆盖：installer/probe 使用代理和 allowlisted env；非零 login、空 catalog、timeout、畸形输出都不保存；异常和输出不得包含 proxy username/password。

- [ ] **步骤 2：运行红灯**

运行：

```powershell
python -m pytest tests/hermes_cli/test_antigravity_setup.py -q
```

预期：安装 URL、显示名解析和 fallback/no-write 测试失败。

- [ ] **步骤 3：最小实现**

在 `setup.py` 提取纯函数：

```python
_MODEL_SLUG = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")

def parse_antigravity_models(stdout: str) -> list[str]:
    models = []
    for raw in stdout.splitlines():
        first = raw.strip().lstrip("-*• ").split(maxsplit=1)[0] if raw.strip() else ""
        if first and _MODEL_SLUG.fullmatch(first) and first not in models:
            models.append(first)
    return models
```

删除全部硬编码模型 fallback。`agy models` 在 login 重试后仍为空即返回失败。恢复官方 installer URL。下载、installer、`--version`、`auth login`、`models` 全部使用 `build_setup_env(proxy_url)`。所有错误先走项目 secret/URL credential redaction。

配置写回读取原始用户配置，使用现有 comment-preserving 原子写入；只有 catalog、选择和最终确认全部成功后才写 `.env`/`config.yaml`。

- [ ] **步骤 4：运行绿灯与回归**

```powershell
python -m pytest tests/hermes_cli/test_antigravity_setup.py tests/agent/backends/test_router.py -q
python -m compileall -q agent/backends/setup.py agent/backends/config.py
```

预期：全部通过。

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/setup.py agent/backends/config.py tests/hermes_cli/test_antigravity_setup.py
git commit -m "fix: honor official Antigravity setup contract"
```

### 任务 2：恢复 `hermes model` 的 setup-only Antigravity 入口

**文件：**
- 修改：`hermes_cli/main.py`
- 修改：`hermes_cli/model_setup_flows.py`
- 修改：`hermes_cli/models.py`（只保留“不属于 canonical provider”的约束）
- 测试：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：编写失败 E2E**

测试真实 provider picker 两级选择：第一层 Google，第二层 Antigravity。断言调用 `_model_flow_antigravity`，但 `antigravity-cli` 不出现在 `CANONICAL_PROVIDERS`。

写入 `.env` 的 `OPENAI_BASE_URL` 和原生 `model`/fallback/auxiliary 配置，执行选择后断言全部保持原值。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/hermes_cli/test_model_provider_persistence.py -k antigravity -q
```

预期：picker 找不到 Antigravity action。

- [ ] **步骤 3：实现一个虚拟 setup action**

不要把 Antigravity 加回 `CANONICAL_PROVIDERS`。在 `select_provider_and_model()` 构造 Google 子菜单时追加一个 setup-only member：

```python
if gid == "google":
    members = [*members, "antigravity-cli"]
    provider_labels["antigravity-cli"] = "Google Antigravity CLI (AI Pro)"
```

保留现有 `_model_flow_antigravity()` dispatch。把 `antigravity-cli` 加入 provider-switch cleanup 排除集合，确保 `_clear_stale_openai_base_url()` 不运行。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/hermes_cli/test_model_provider_persistence.py tests/hermes_cli/test_gemini_provider.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add hermes_cli/main.py hermes_cli/model_setup_flows.py hermes_cli/models.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "fix: expose Antigravity as a setup-only model action"
```

### 任务 3：统一 profile-aware 配置所有权

**文件：**
- 修改：`gateway/interactive_backend.py`
- 修改：`gateway/platforms/api_server.py`
- 修改：`tui_gateway/interactive_backend.py`
- 修改：`tests/gateway/test_antigravity_backend.py`
- 修改：`tests/gateway/test_antigravity_message_auth.py`
- 修改：`tests/tui_gateway/test_antigravity_backend.py`

- [ ] **步骤 1：编写生产类型失败测试**

Gateway 测试必须使用真实 `GatewayConfig`/`PlatformConfig`，证明 Enum 平台键不会进入 backend resolver。Turn 测试给 `TurnContext.user_config` 设置：

```python
{"agent_backends": {"default": "antigravity"}}
```

并断言 `agy` 被调用。

增加两个 profile 的 `/message` 测试，分别使用不同 backend/model/proxy，断言 router/pool 不共享。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/tui_gateway/test_antigravity_backend.py -q
```

预期：真实 `GatewayConfig` 仍解析为 Hermes，profile 隔离失败。

- [ ] **步骤 3：删除配置猜测**

普通 Gateway turn 直接使用已经 profile-scoped 的 `ctx.user_config`；删除 `dataclasses.asdict(GatewayConfig)` 路径。runner 保存 `_backend_routers: dict[str, BackendRouter]`，按 `request.profile` 取 router。

API server 根据 `_api_request_profile` 解析 profile，使用 `hermes_cli.profiles.get_profile_dir()` 和 `hermes_constants.set_hermes_home_override()` 临时加载该 profile 的 `load_config_readonly()`，并在 `finally` reset token。router 同样按 profile 存储。

TUI 保留 session-owned router，但配置必须来自 `_load_cfg()`/session profile，不能读取 agent 上不存在的属性。

- [ ] **步骤 4：运行绿灯与 profile 回归**

```powershell
python -m pytest tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/gateway/test_multiplex_session_db_profile_scope.py tests/tui_gateway/test_antigravity_backend.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add gateway/interactive_backend.py gateway/platforms/api_server.py tui_gateway/interactive_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/tui_gateway/test_antigravity_backend.py
git commit -m "fix: scope Antigravity routers to effective profiles"
```

### 任务 4：修复 pool 租约、恢复和关闭语义

**文件：**
- 修改：`agent/backends/pool.py`
- 测试：`tests/agent/backends/test_pool.py`

- [ ] **步骤 1：编写确定性竞态测试**

使用 Event barrier 创建同 session 的 active turn、一个 waiter 和第三个新 session。断言 waiter 存在时原 entry 不可被 LRU/idle cleanup 驱逐。

模拟 `session.close()` 失败，断言 entry 仍可追踪，`active_count` 不减少。模拟活着的 session 抛 `RuntimeError`，断言不恢复、不重复发送；只有 `fatal is True and alive is False` 才恢复一次。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/agent/backends/test_pool.py -q
```

- [ ] **步骤 3：用租约计数替换 busy bool**

`_PoolEntry` 使用 `leases: int`。在 pool lock 内获取/创建 entry 并 `leases += 1`，turn 完成后在 lock 内减一。LRU 和 idle cleanup 只处理 `leases == 0`。

`close_session()` 先标记 closing，取得 entry turn lock；只有 `session.close()` 成功后才从字典删除。关闭失败保留 entry 并抛出错误，不吞掉。eviction 从 global lock 中取出候选，释放 lock 后关闭，成功后再 CAS 删除。

恢复条件严格为 transport fatal + process dead。删除宽泛的 `except (RuntimeError, OSError)` 自动恢复。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/agent/backends/test_pool.py tests/agent/backends/test_antigravity.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/pool.py tests/agent/backends/test_pool.py
git commit -m "fix: make Antigravity pool lifecycle race-safe"
```

### 任务 5：限制 transport 资源并接通 interrupt

**文件：**
- 修改：`agent/backends/antigravity.py`
- 修改：`cli.py`
- 修改：`tui_gateway/server.py`
- 修改：`gateway/run.py`
- 修改：`gateway/platforms/api_server.py`
- 修改：`tests/agent/backends/test_antigravity.py`
- 修改：`tests/cli/test_antigravity_backend.py`
- 修改：`tests/tui_gateway/test_antigravity_backend.py`
- 修改：`tests/gateway/test_antigravity_backend.py`

- [ ] **步骤 1：编写失败测试**

覆盖：queue 最多 1024 events；单 turn 最多固定事件数和总字节；queue flood/turn budget 触发 fatal 并回收完整进程树；proxy URL userinfo 在 stderr/tool/error 中被删除。

分别从 CLI interrupt、TUI `session.interrupt`、Gateway stop 和 API run stop 入口触发，断言调用正确 router 的 `interrupt(profile, platform, session_id)`，而不是只调用 AIAgent。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/agent/backends/test_antigravity.py tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py -q
```

- [ ] **步骤 3：最小资源边界**

使用 `queue.Queue(maxsize=1024)`。reader 遇到 Full 时设置受锁保护的 `_reader_failure`；consumer 用短轮询同时检查 queue、failure 和 deadline。定义 `MAX_TURN_EVENTS`、`MAX_TURN_BYTES`，在 `_read_turn` 累加并 fail closed。

调用：

```python
redact_sensitive_text(
    value,
    force=True,
    code_file=False,
    redact_url_credentials=True,
)
```

在所有现有 interrupt chokepoint 先解析 effective backend；Antigravity 调 router interrupt，Hermes 保持原路径。CLI/TUI/Gateway/API teardown 均 shutdown 自己拥有的 router/pool。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/agent/backends/test_antigravity.py tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/antigravity.py cli.py tui_gateway/server.py gateway/run.py gateway/platforms/api_server.py tests/agent/backends/test_antigravity.py tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py
git commit -m "fix: bound and interrupt Antigravity transports"
```

### 任务 6：修复媒体、transcript 和 session 恢复不变量

**文件：**
- 修改：`agent/backends/antigravity.py`
- 修改：`agent/backends/router.py`
- 修改：`cli.py`
- 修改：`tui_gateway/interactive_backend.py`
- 修改：`gateway/interactive_backend.py`
- 修改：`tests/cli/test_antigravity_backend.py`
- 修改：`tests/tui_gateway/test_antigravity_backend.py`
- 修改：`tests/gateway/test_antigravity_backend.py`

- [ ] **步骤 1：编写端到端失败测试**

每个表面发送一轮后检查 SessionDB：恰好一个 user row、一个 assistant row、一个 backend/conversation ID。resume 后恢复 backend override 和 `--conversation`；`/new` 关闭旧进程并继承 platform/global 默认。

Gateway 给出一个通过 canonical media policy 的 staged 文件，fake `agy` 必须在收到的 user content 中看到路径；拒绝路径只出现固定 unavailable note，不出现原始敏感路径。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py -q
```

- [ ] **步骤 3：单一持久化所有者**

由 surface 负责 transcript，由 router 只负责 backend metadata，或反之；选择一个并删除重复 append。恢复 session 时从 SessionDB 加载 `agent_backend` 和 `backend_conversation_id` 交给 pool。

在 `AntigravitySession.run_turn()` 写 stdin 前构造文本：

```text
<user text>

Attached local files validated by Hermes:
- <resolved safe path>
```

只使用 `BackendTurnRequest.media_paths` 中已经通过 canonical policy 的路径。Gateway/TUI/CLI 使用各自 session cwd，不直接使用进程 `os.getcwd()`。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/test_hermes_state.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/antigravity.py agent/backends/router.py cli.py tui_gateway/interactive_backend.py gateway/interactive_backend.py tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py
git commit -m "fix: preserve Antigravity session and media invariants"
```

### 任务 7：最终验证和真实 `agy` smoke

- [ ] **步骤 1：运行 Antigravity 聚焦套件**

```powershell
python -m pytest tests/agent/backends tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/test_hermes_state.py -q
```

- [ ] **步骤 2：运行跨表面回归**

```powershell
python -m pytest tests/hermes_cli/test_commands.py tests/cli/test_cli_retry.py tests/test_tui_gateway_server.py tests/gateway/test_stream_events.py tests/gateway/test_turn_lease.py tests/agent/backends/test_noninteractive_isolation.py -q
```

若 `peer_messaging` 两项基线仍失败，必须在未修改基线提交上复现后才能标为无关。

- [ ] **步骤 3：运行静态和 Desktop 检查**

```powershell
python -m compileall -q agent/backends tui_gateway gateway hermes_cli cli.py hermes_state.py
git diff --check
npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts
npm --prefix apps/desktop install
npm --prefix apps/desktop run typecheck
```

- [ ] **步骤 4：真实本机 smoke**

通过 `hermes gateway backend setup antigravity` 使用官方 installer/代理，手工完成 AI Pro 登录。运行：

1. CLI 两轮，确认同 PID/conversation ID。
2. TUI 两轮及 interrupt。
3. `/backend hermes` 切回。
4. QQBot/Telegram allowlisted 用户一轮。
5. `/message` 无 key 返回 401；有效 key 两轮保持上下文。
6. `/new`、关闭网关后无孤儿 `agy`。

- [ ] **步骤 5：两阶段代码审查**

先做规格合规审查，再做安全/并发/跨平台代码质量审查。所有 Critical/Important 清零后才能进入部署。

- [ ] **步骤 6：确认提交边界**

```powershell
git status --short
git log --oneline --max-count=8
```

预期：工作树为空；每个修复任务已经各自提交，不再创建无内容的“验证提交”。

## 完成标准

- 官方 installer URL 可访问，不存在硬编码模型 fallback。
- `hermes model` 可选择 Antigravity，但它不属于 canonical provider。
- CLI/TUI/Gateway/API 都使用 profile-scoped Mapping 和持久 router。
- `/message` 所有 Antigravity模式都在 spawn 前要求 API key。
- pool 无 active/waiter eviction、关闭失败不丢 tracking、只恢复确认死亡 transport。
- 所有 interrupt/teardown 回收完整进程树。
- 每轮 transcript 无重复，resume/new/conversation ID 正确。
- media 通过 canonical policy 并真正进入 `agy` prompt。
- Python、Desktop、静态检查和真实 `agy` smoke 全部通过。
- 工作树干净，修复提交推送前再次核对本地/远程 SHA。
