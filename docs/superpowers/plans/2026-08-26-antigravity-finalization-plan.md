# Antigravity Backend 最终收尾实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 消除 Antigravity backend 最后的重复 turn 和进程跟踪风险，完成真实表面/跨平台验收，并将可部署提交安全推送到 fork。

**架构：** 保留现有 BackendRouter、AntigravitySessionPool 和表面桥。恢复只允许发生在“上一轮已成功、当前轮尚未写入 stdin、旧进程在轮间死亡”的安全窗口；任何当前轮已提交后的错误都不重放。所有 close 路径采用 close-success 后 CAS 删除，失败则保留可追踪 entry。

**技术栈：** Python 3.11、stdlib subprocess/threading/queue、pytest、Vitest、TypeScript、Windows Scheduled Tasks、Linux user systemd。

---

## 当前已验证基线

基准提交：`ffac45f89d2044124b0a09393e92f8e398b4e91c`

```text
聚焦：464 passed, 2 skipped
跨表面：660 passed, 2 个 peer_messaging 基线失败
Desktop slash：27 passed
真实 agy：1.1.20，14 模型，两轮及 router 重建恢复成功
```

执行前必须确认工作树干净：

```powershell
git status --short --branch
git diff --check
```

预期：无未提交文件。若存在修改，先与所有者确认并保存，不得 reset 或 checkout 丢弃。

### 任务 1：将恢复限定为安全的轮间窗口

**文件：**
- 修改：`agent/backends/antigravity.py`
- 修改：`agent/backends/pool.py`
- 修改：`tests/fixtures/fake_agy.py`
- 修改：`tests/agent/backends/test_antigravity.py`
- 修改：`tests/agent/backends/test_pool.py`

- [ ] **步骤 1：编写失败的重复提交测试**

Fake `agy` 增加按 session 写入计数文件的模式。测试当前轮收到 user event 后返回 ERROR并退出，断言同一 prompt 只出现一次：

```python
def test_post_submit_terminal_error_is_never_replayed(tmp_path):
    counter = tmp_path / "turns.jsonl"
    pool = AntigravitySessionPool(_config(extra_env={"FAKE_AGY_COUNTER": str(counter)}))
    with pytest.raises(RuntimeError):
        pool.run_turn(_request("ERROR_AFTER_ACCEPT"), lambda event: None)
    assert counter.read_text(encoding="utf-8").splitlines() == ["ERROR_AFTER_ACCEPT"]
```

补充测试：写入后 broken pipe、malformed result、未知 status、timeout 都不重放；成功 turn 后进程自行退出，下一 turn 在写入前使用 conversation ID恢复且只发送一次。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/agent/backends/test_pool.py tests/agent/backends/test_antigravity.py -k "replay or resume_safe or after_accept" -q
```

预期：当前 fatal/dead 广义恢复导致 counter 出现两条，测试失败。

- [ ] **步骤 3：实现显式恢复状态机**

在 `AntigravitySession` 暴露不可变快照：

```python
@dataclass(frozen=True)
class AntigravitySessionState:
    started: bool
    alive: bool
    last_turn_succeeded: bool
    conversation_id: str
```

生命周期：

- spawn 前：`last_turn_succeeded=False`。
- 收到 SUCCESS result 后：`last_turn_succeeded=True`。
- 开始写下一 user event 前：重新设为 False。
- `resume_safe` 仅为 `started and not alive and last_turn_succeeded and conversation_id`。

Pool 在调用 `session.run_turn()` **之前** 检查 `resume_safe`，必要时创建一次 `--conversation` session。删除 `except RuntimeError/OSError` 中对当前 turn 的自动恢复；调用开始后任何异常原样失败并清理，不重试。

- [ ] **步骤 4：运行绿灯与恢复回归**

```powershell
python -m pytest tests/agent/backends/test_pool.py tests/agent/backends/test_antigravity.py -q
```

预期：全部通过；原有 `EXIT_AFTER_RESULT` 轮间恢复继续通过。

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/antigravity.py agent/backends/pool.py tests/fixtures/fake_agy.py tests/agent/backends/test_antigravity.py tests/agent/backends/test_pool.py
git commit -m "fix: prevent replay of submitted Antigravity turns"
```

### 任务 2：统一所有 pool 删除路径的关闭跟踪

**文件：**
- 修改：`agent/backends/pool.py`
- 修改：`tests/agent/backends/test_pool.py`

- [ ] **步骤 1：编写失败测试矩阵**

对以下路径参数化 close failure：explicit close、idle cleanup、LRU eviction、fatal release、recovery abandon、recovery second failure、shutdown。

```python
@pytest.mark.parametrize("operation", CLOSE_OPERATIONS)
def test_failed_close_retains_trackable_entry(operation, pool_with_failing_close):
    key, pid = pool_with_failing_close.seed(operation)
    with pytest.raises(RuntimeError):
        pool_with_failing_close.run(operation)
    assert pool_with_failing_close.pool.has_entry(*key)
    assert pool_with_failing_close.pool.session_pid(*key) == pid
```

为测试增加只读 `has_entry(profile, platform, session_id)`，不要暴露 mutable entry。

- [ ] **步骤 2：运行红灯**

```powershell
python -m pytest tests/agent/backends/test_pool.py -k "failed_close or trackable" -q
```

- [ ] **步骤 3：实现单一 close helper**

新增 `_close_and_remove(key, entry, *, interrupt=False) -> bool`：

1. 不持有 global lock，取得 entry turn lock。
2. 可选 interrupt。
3. 调用 close。
4. close成功后在 global lock 内 CAS检查 identity、leases==0，再删除。
5. close失败保留 entry并抛出安全 RuntimeError。

explicit close、cleanup、eviction、fatal release、recovery cleanup、shutdown全部调用该 helper。`shutdown()` 返回失败 key列表或抛出聚合错误，不能假装成功。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/agent/backends/test_pool.py tests/agent/backends/test_antigravity.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add agent/backends/pool.py tests/agent/backends/test_pool.py
git commit -m "fix: preserve tracking when Antigravity close fails"
```

### 任务 3：完成生产表面生命周期 E2E

**文件：**
- 修改：`tests/cli/test_antigravity_backend.py`
- 修改：`tests/tui_gateway/test_antigravity_backend.py`
- 修改：`tests/gateway/test_antigravity_backend.py`
- 修改：`tests/gateway/test_antigravity_message_auth.py`
- 仅测试证明缺陷时修改：`cli.py`
- 仅测试证明缺陷时修改：`tui_gateway/server.py`
- 仅测试证明缺陷时修改：`gateway/run.py`
- 仅测试证明缺陷时修改：`gateway/platforms/api_server.py`

- [ ] **步骤 1：建立真实 chokepoint E2E**

每个测试从正式入口触发，不直接调用 interrupt helper：

- CLI 输入循环启动 TIMEOUT turn，再走 CLI interrupt处理。
- TUI `prompt.submit` 启动 TIMEOUT，再调用 `session.interrupt` RPC。
- Gateway 正式 stop/interrupt dispatch 中断 Telegram turn。
- `/message` 通过真实 aiohttp request：无 key 401且 spawn count 0；有效 bearer 两轮同 conversation ID。

所有测试断言 parent/child process退出、pool entry状态正确、后续 `/new` 可建新会话。

- [ ] **步骤 2：运行测试并判断是否需要代码修改**

```powershell
python -m pytest tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py -q
```

若测试直接通过，不修改生产文件，只提交强化测试。若失败，只修正式 chokepoint，不增加第二个 helper。

- [ ] **步骤 3：补齐 resume/new/transcript 不变量**

E2E 执行：turn 1 -> 销毁 router -> 新 router/同 SessionDB -> turn 2，断言 `--conversation` 使用存储ID且消息严格为 user/assistant/user/assistant。执行 `/new` 后断言旧进程关闭、新 session不携带旧ID并继承平台/global backend。

- [ ] **步骤 4：验证**

```powershell
python -m pytest tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/test_hermes_state.py -q
```

- [ ] **步骤 5：提交**

```powershell
git add tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py cli.py tui_gateway/server.py gateway/run.py gateway/platforms/api_server.py
git commit -m "test: cover Antigravity production lifecycle"
```

### 任务 4：完成全自动验证和双审查

**文件：**
- 不预设生产文件修改
- 允许修复：本分支引入且被验证发现的缺陷

- [ ] **步骤 1：运行聚焦套件**

```powershell
python -m pytest tests/agent/backends tests/cli/test_antigravity_backend.py tests/tui_gateway/test_antigravity_backend.py tests/gateway/test_antigravity_backend.py tests/gateway/test_antigravity_message_auth.py tests/hermes_cli/test_antigravity_setup.py tests/hermes_cli/test_model_provider_persistence.py tests/test_hermes_state.py -q
```

- [ ] **步骤 2：运行跨表面套件**

```powershell
python -m pytest tests/hermes_cli/test_commands.py tests/cli/test_cli_retry.py tests/test_tui_gateway_server.py tests/gateway/test_stream_events.py tests/gateway/test_turn_lease.py tests/agent/backends/test_noninteractive_isolation.py -q
```

`peer_messaging` 两项若仍失败，必须在 `1294af2ed0` 基线上运行同一 test node并记录相同失败，才能标记为基线。

- [ ] **步骤 3：安装 Desktop 依赖并完成类型检查**

```powershell
npm --prefix apps/desktop install
npx vitest run apps/desktop/src/lib/desktop-slash-commands.test.ts
npm --prefix apps/desktop run typecheck
```

依赖安装仅产生 ignored `node_modules`/lockfile一致性输出；不得提交意外 lockfile变更。

- [ ] **步骤 4：静态检查**

```powershell
python -m compileall -q agent/backends tui_gateway gateway hermes_cli cli.py hermes_state.py
git diff --check
git status --short
```

预期：全部退出0，工作树干净。

- [ ] **步骤 5：规格合规审查**

审查范围从本计划开始前提交到当前HEAD。逐项核对计划任务 1–3，不接受报告自证，直接阅读代码和测试。发现任何缺失/多余功能，原实现者修复后重新审查。

- [ ] **步骤 6：代码质量审查**

规格审查通过后，检查：重复 turn、锁顺序、进程树、secret env/URL、profile隔离、prompt cache/角色交替、SessionDB重复写、Windows/POSIX。Critical/Important必须清零。

### 任务 5：Windows 本地真实验收

**前置：** 任务 1–4全部通过，工作树干净。

- [ ] **步骤 1：验证官方安装与认证**

```powershell
agy --version
agy models
```

记录版本和模型，不记录token。若需重装，只通过：

```powershell
hermes gateway backend setup antigravity
```

设置正向代理后确认 installer/version/auth/models只收到 allowlist环境。

- [ ] **步骤 2：经典 CLI**

在临时 profile运行 `/backend antigravity`，发送两轮固定回复，记录同 PID/conversation ID；测试 Ctrl+C interrupt、`/new`、`/backend hermes`。确认原生 model/provider/base URL未改变。

- [ ] **步骤 3：TUI/Desktop/Dashboard**

分别发送两轮，验证 streaming/tool event、interrupt、resume、backend command。Dashboard只验证嵌入 TUI，不创建React第二聊天实现。

- [ ] **步骤 4：本地 Gateway**

QQBot/Telegram allowlisted 用户发送文本和一个安全文件/图片；确认路径进入 `agy` 且敏感路径被拒绝。调用本地 `/message`：无key 401，有key两轮同上下文。

- [ ] **步骤 5：清理检查**

关闭CLI/TUI/Gateway，使用进程列表确认无孤儿 `agy`。失败则回到任务2，不继续远程部署。

### 任务 6：host 130 验收、推送和部署

**前置：** Windows真实验收通过，用户允许在130完成 `agy` OAuth登录。

- [ ] **步骤 1：推送功能分支，不创建PR**

```powershell
git push -u origin feature/antigravity-backend
$local = git rev-parse HEAD
$remote = (git ls-remote origin refs/heads/feature/antigravity-backend).Split()[0]
if ($local -ne $remote) { throw "remote SHA mismatch" }
```

- [ ] **步骤 2：备份130**

在130停止 user service前记录当前PID/健康状态。将 `/usr/local/lib/hermes-agent` 改名为带时间戳备份；保留 `/root/.hermes` 不变。验证目标绝对路径后再移动。

- [ ] **步骤 3：部署源码和editable环境**

从已验证HEAD创建 `git archive`，本地与130核对SHA-256；解包到 staging，迁移现有 `venv`、`.hermes-runtime`、`node_modules`，运行 `uv pip install --no-deps -e` 和 `compileall`，再原子切换目录。

- [ ] **步骤 4：安装/登录 `agy`**

先确认 Gateway 实际用户：

```powershell
ssh 130 'systemctl --user show hermes-gateway -p User -p MainPID; pid=$(systemctl --user show hermes-gateway -p MainPID --value); ps -o user= -p "$pid"'
```

当前部署预期为 `root` user service。必须以同一用户完成登录，不能在本地登录后复制 token，也不能用另一个 SSH 用户登录再让 root service 读取其 keyring。

使用交互式 TTY运行 setup：

```powershell
ssh -t 130 'export HERMES_HOME=/root/.hermes; export PATH=/root/.local/bin:/usr/local/bin:$PATH; /usr/local/lib/hermes-agent/venv/bin/hermes gateway backend setup antigravity'
```

向导步骤：

1. 输入130可访问的标准正向代理 URL；无代理直接回车。
2. 未安装时确认运行 Google 官方 installer。
3. setup 启动 `agy auth login` 后，SSH终端显示一次性授权 URL。
4. 在操作人员本机浏览器打开该 URL，选择具有 Google AI Pro 权益的账号并授权。
5. 浏览器显示一次性 authorization code；将 code 粘贴回原 SSH终端并回车。
6. 不把 URL/code/token写入聊天、日志、config.yaml或部署脚本。
7. setup 继续执行 `agy models`；选择真实目录中的模型、effort和permission模式。

若 URL 被终端换行，完整复制从 `https://` 开始到末尾的所有字符，不手工删减 query参数。若浏览器返回账号不符合资格，停止部署并更换有AI Pro权益的账号，不修改 Hermes代码绕过。

登录后用非交互命令验证同一用户可见认证：

```powershell
ssh 130 'export PATH=/root/.local/bin:/usr/local/bin:$PATH; agy --version; agy auth status; agy models'
```

再通过同一 user systemd manager 验证服务环境也能访问凭据：

```powershell
ssh 130 'agy_path=$(command -v agy); test -n "$agy_path"; systemd-run --user --wait --pipe --collect "$agy_path" -p "Reply with exactly: OK" --output-format json --model gemini-3.7-flash-medium --print-timeout 2m'
```

预期 JSON：`status` 为 `SUCCESS` 且 `response` 为 `OK`。输出不得包含 access/refresh token。

如果需要切换账号：先在交互式 `agy` 中执行 `/logout`，退出后重新运行上述 `agy auth login`。若服务仍以root运行，选择 `trusted` 前必须再次向用户确认其等价于让 Antigravity 以root免审批执行主机命令；默认先用 `strict` 完成 smoke。

- [ ] **步骤 5：130真实 smoke**

验证 API health、QQBot Ready、Telegram连接状态、`/message`门禁和两轮上下文、Gateway restart/resume、safe file、interrupt。确认关闭测试会话后无孤儿 `agy`。

- [ ] **步骤 6：最终发布判定**

比较本地/130关键源码SHA和分支HEAD。只有所有测试、双审查、两台主机smoke和回滚备份均成功，才能报告部署完成。失败时恢复备份并保留日志，不修改用户配置来掩盖失败。

## 最终完成标准

- 当前 turn 已提交后的任何错误都不会自动重放。
- 仅成功轮间进程死亡可通过存储 conversation ID恢复一次。
- 所有 close失败保持 pool tracking，可被重试/诊断。
- CLI/TUI/Gateway/API正式 interrupt路径均终止完整进程树。
- resume/new/transcript/media/profile/auth不变量有生产路径E2E。
- Python、Desktop、静态检查全部通过；基线失败有base证据。
- Windows与130真实 `agy` smoke通过且无孤儿进程。
- 分支已推送到fork，本地/远程/部署SHA一致；不创建PR。
