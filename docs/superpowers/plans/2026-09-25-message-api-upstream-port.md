# Message API 上游移植实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在最新上游基线上保留 fork 的 `/message` 通话/显式命令契约，并在 Dashboard 与 Desktop 管理独立的通话密钥，支持默认关闭的强制聊天密钥开关。

**架构：** API Server 只负责路由与现有 Agent 执行；`gateway/platforms/message_api.py` 承载 `/message` 解析、授权、执行令牌和历史投影；`gateway/platforms/message_api_keys.py` 是两套管理传输共用的 profile 范围 SQLite 密钥与开关服务。Dashboard 经现有登录门禁调用 FastAPI 路由，Desktop 经 profile-scoped JSON-RPC 调用同一服务。专用通话密钥从不参与命令授权；新开关不写 `config.yaml`，每次聊天从状态库读取。

**技术栈：** Python 3.11+、aiohttp、FastAPI、SQLite、pytest（仅 `scripts/run_tests.sh`）、React/TypeScript、Vitest、生成的 JSON-RPC 契约。

---

## 文件职责

- 创建 `gateway/platforms/message_api_keys.py`、`tests/gateway/test_message_api_keys.py`：密钥生成/摘要校验/列表/撤销；按 `get_hermes_home()` 绑定私有 SQLite 状态，事务处理并发写入；同一 SQLite 服务提供 `require_chat_key` 的读写，且不碰 `config.yaml`。
- 创建 `gateway/platforms/message_api.py`、`tests/gateway/test_message_api.py`：原 `/message` 请求、命令授权、执行令牌、消息历史；与 `APIServerAdapter` 的现有 Agent/SessionDB 方法协作。
- 修改 `gateway/platforms/api_server.py`、`tests/gateway/test_api_server.py`：初始化配置、注册路由、窄连接到 mixin；继续使用已移植的双栈/远程访问控制。
- 创建 `hermes_cli/web_routers/message_keys.py`、`tests/hermes_cli/test_web_message_keys.py`；修改 `hermes_cli/web_server.py`：Dashboard 管理路由及 profile/登录边界。
- 创建 `tui_gateway/methods_message_keys.py`、`tui_gateway/contracts/message_keys.py`、`tests/tui_gateway/test_message_keys.py`；修改 `tui_gateway/server.py`、`tui_gateway/contracts/__init__.py`、生成的 `apps/shared/src/gateway-contract.generated.ts` 和 `apps/shared/src/gateway-contract.openrpc.json`：Desktop RPC 传输及静态类型。
- 创建 `web/src/components/MessageKeysPanel.tsx` 及 `.test.tsx`；修改 `web/src/pages/EnvPage.tsx`、`web/src/lib/api.ts`、`web/src/i18n/{types,en,zh}.ts`：Dashboard Keys 页面管理入口及双语文案。
- 创建 `apps/desktop/src/app/settings/message-keys-settings.tsx` 及 `.test.tsx`；修改 `apps/desktop/src/app/settings/{keys-settings,index}.tsx`、`apps/desktop/src/i18n/{types,en,zh}.ts`：Desktop Keys 子页，沿用选中连接/profile 的请求通道。
- 修改 `website/docs/user-guide/features/api-server.md` 与相关测试：鉴权矩阵、开关的 SQLite 保存/备份语义和密钥一次性显示；在最终移植时对账原 `main` 的未提交 `agent_mode` 改动。

计划依据：[已批准规格](../specs/2026-09-25-message-api-upstream-port-design.md)。本计划只交付 `/message` 子项目；Gemini、WebUI 全面汉化、Windows/PM 的移植与最终 `main` 合并按 [总计划](../../integration/2026-09-25/upstream-port-plan.md) 分别验收。原 `F:\Documents\Project\hermes-agent` 工作区的未提交改动不得覆盖。所有命令在 `C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent` 执行。

### 任务 1：持久化独立通话密钥

**文件：** 创建 `gateway/platforms/message_api_keys.py`、`tests/gateway/test_message_api_keys.py`。

- [x] **步骤 1：红测。** 添加下列行为测试，用临时 `HERMES_HOME` 隔离状态；同一文件再测两次创建与跨进程打开的列表、撤销后即时校验失败、其他 profile 不可见、数据库文件无明文和 POSIX 0600。

```python
def test_created_key_is_shown_once_and_revocable(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from gateway.platforms import message_api_keys as keys
    issued = keys.create_key("router")
    assert issued["key"].startswith("hmmsg_")
    assert keys.validate_key(issued["key"]) is True
    assert all("key" not in row for row in keys.list_keys())
    assert issued["key"] not in (tmp_path / "message_api_keys.sqlite3").read_bytes().decode("latin1")
    assert keys.revoke_key(issued["id"]) is True
    assert keys.validate_key(issued["key"]) is False
```

- [x] **步骤 2：确认红。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/gateway/test_message_api_keys.py'`；预期为模块缺失/断言失败，不是 collection 被环境阻断。
- [x] **步骤 3：最小实现。** 在新模块提供固定四个函数 `create_key(name) -> {id,name,created_at,key}`、`list_keys() -> [{id,name,created_at}]`、`revoke_key(id) -> bool`、`validate_key(key) -> bool`。生成 `hmmsg_` + `secrets.token_urlsafe(32)`，以 SHA-256 存储摘要，用 `hmac.compare_digest` 校验；使用 `sqlite3` 事务和默认 DELETE journal，建库时 `os.open(path, O_CREAT|O_EXCL, 0o600)`，连接前校验路径不为符号链接。存储目录使用 `get_hermes_home()`，不读写 `config.yaml` 或 `.env`。数据库不可读/损坏时拒绝创建、校验和撤销，绝不将空列表写回覆盖旧记录；错误不包含明文。名称只允许 1–80 个可打印字符。
- [x] **步骤 4：转绿并提交。** 运行步骤 2 的完整测试，再运行 `git diff --check`；预期均 exit 0。提交 `git add gateway/platforms/message_api_keys.py tests/gateway/test_message_api_keys.py`；`git commit -m "feat(message): add profile-scoped chat key store"`。

- [x] **步骤 5：开关服务红测。** 在同一测试文件加入 `get_policy()["require_chat_key"] is False`；创建密钥后调用 `set_policy(True)`，另一个进程立即读到 true，已有密钥仍可验证；再次设置 false 即时恢复。对 `config.yaml` 预置任意字段并记录字节，设置开关前后必须逐字节不变；在两个进程交错设置开关时不能出现损坏库或陈旧旧值回写。预置非 SQLite/损坏库时读取必须抛出存储错误，不能退回默认 false。运行步骤 2 的命令并确认这些新增测试红。
- [x] **步骤 6：开关服务转绿并提交。** 在 `message_api_keys.sqlite3` 内创建仅有一行的 `message_policy` 表（`id=1, require_chat_key=0|1`）；`get_policy()` 缺库返回 false、损坏库抛错，`set_policy(bool)` 在 SQLite 事务中 `INSERT ... ON CONFLICT(id) DO UPDATE`。只处理当前 profile 的 `get_hermes_home()`，不再调用 `require_readable_config_before_write()`/`save_config()`。运行步骤 2 的 canonical 测试与 `git diff --check`，预期零失败；提交 `git add gateway/platforms/message_api_keys.py tests/gateway/test_message_api_keys.py`、`git commit -m "feat(message): persist optional chat key requirement in SQLite"`。**原计划已写入 YAML 的两个隔离分支提交不得带入最终交付行为**：以本步移除 YAML 调用并通过不写配置测试为准，不改原 `main`。

任务 1 审查记录：规格复审 PASS；质量复审 PASS。Windows 上指定测试 17 通过、2 项 POSIX 用例跳过。条件性加固：仅在运营方允许不可信用户写 `HERMES_HOME` 且高权限服务访问该目录时，数据库路径的 symlink TOCTOU 成为跨权限风险；当前默认 home 为所有者权限，未把此假设性部署模型当作本次阻断。任务 2 在接入外部 `chat_key` 时须对输入长度做限制并覆盖畸形 Unicode。

### 任务 2：恢复聊天与命令契约

**文件：** 创建 `gateway/platforms/message_api.py`、`tests/gateway/test_message_api.py`；修改 `gateway/platforms/api_server.py`、`tests/gateway/test_api_server.py`。

- [ ] **步骤 1：红测聊天。** 注册真实 aiohttp route 后测试默认 `require_chat_key=false` 的无密钥聊天调用 `_run_agent` 一次，`session_id` 回退到 `sender_id`；开关为 true 时无密钥返回 401 且 `_run_agent` 未调用，合法 `X-Hermes-Message-Key` 或请求体 `chat_key` 通过；在旧 `api_key` 字段中传入专用通话密钥也只允许聊天。示例：

```python
import pytest
from unittest.mock import AsyncMock
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter

@pytest.mark.asyncio
async def test_chat_key_never_authorizes_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from gateway.platforms.message_api_keys import create_key
    key = create_key("peer")["key"]
    adapter = APIServerAdapter(PlatformConfig(
        enabled=True, extra={"key": "test-api-key-123456789012345",
                             "message_api": {"allow_command_execution": True}}))
    adapter._run_agent = AsyncMock(return_value=({"final_response": "ok"}, {}))
    app = web.Application()
    app.router.add_post("/message", adapter._handle_message_api)
    async with TestClient(TestServer(app)) as client:
        response = await client.post("/message", json={
            "message": "hi", "command": "id", "chat_key": key})
        body = await response.json()
    assert body["reply"] == "ok"
    assert body["command"]["authorized"] is False
    assert body["command"]["executed"] is False
```

- [ ] **步骤 2：确认红。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/gateway/test_message_api.py tests/gateway/test_api_server.py -k message'`；预期新路由 404 或相关断言失败。
- [ ] **步骤 3：移植逻辑。** 从 fork `main` 的 `APIServerAdapter._handle_message_api` 与 `_MessageTokenStore` 提取到 `message_api.py` 的 `MessageApiMixin`，保持 `message_api:` 会话和用户标记、历史读取、短期执行令牌、错误响应形态；`api_server.py` 只在类继承/`__init__`/`_http_route_table()` 接入 `POST /message` 与历史 GET。现有 `message_api.api_keys`/Bearer/`exec_token` **只**作为显式命令授权；新的 `message_api_keys.validate_key` **只**参与消息准入。**每次带 `message` 的请求从密钥状态库调用 `get_policy()`，开关变动立即生效；损坏/不可读库拒绝放行，而不是默认为 false。** 撤销同样不缓存。限流使用 API Server 现有并发准入。不要写 `except (json.JSONDecodeError, Exception)`、不要把原始异常 `str(exc)` 发给客户端。
- [ ] **步骤 4：补充边界并转绿。** 同文件添加无效 JSON 400、无效类型 400、禁用入口 404、禁用命令 403、纯命令无凭据 401、聊天加未授权命令返回聊天但不执行、Bearer/旧 key 执行、过期 token 不执行、历史需 Bearer 且不可跨会话/跨 profile、`shared_memory_notes_enabled` 和 `session_history_delivery` 默认关闭/显式开启等行为测试。运行步骤 2 的两文件完整测试（去掉 `-k`），预期零失败；`git diff --check` exit 0。提交 `git add gateway/platforms/message_api.py gateway/platforms/api_server.py tests/gateway/test_message_api.py tests/gateway/test_api_server.py`；`git commit -m "feat(message): preserve chat and command contracts"`。

任务 2 阶段验收：实现提交 `5555882f55`、`d9728e4a01`、`e56ffb6e57`、`cfec58778c`；原规格和代码质量审查 PASS。Windows 隔离工作树重跑三文件测试为 165 通过、0 失败、2 项 POSIX 用例跳过。旧协议对 JSON `null` 视为未提供，新测试确保 `command: null` 不执行命令。用户随后批准改变无身份字段的匿名会话回退；下方任务 2b 的新安全契约未实施/验收前，任务 2 不可作为最终整体 GO。

### 任务 2b：隔离未声明身份的匿名请求

**文件：** 修改 `gateway/platforms/message_api.py`、`tests/gateway/test_message_api.py`。

- [ ] **步骤 1：写红测。** 用真实 aiohttp route 发两次不带 `session_id`/`sender_id` 的消息，断言两次响应的 `session_id` 不同且均不等于 `remote`；复用真实临时 `HERMES_HOME` + SessionDB 断言第二次传给 `_run_agent` 的历史不含第一次内容；对 `sender_id: ""`、`session_id: null` 等缺省形态同样生成独立 ID。另发两次明确 `sender_id: "same-peer"` 的请求，确认沿用原有同一会话续聊规则；显式 `session_id` 优先级高于 sender。纯命令不带身份字段时也不得回到共用 `remote` task_id。
- [ ] **步骤 2：红灯确认。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/gateway/test_message_api.py -k anonymous'`；预期独立性断言失败，而不是依赖/fixture 收集失败。
- [ ] **步骤 3：最小实现。** 只在两个字段都为空时生成 `secrets.token_urlsafe(24)` 前缀的会话别名；响应返回创建后的实际会话 ID。沿用现有 `message_api:` session key 与 `_bind_declared_conversation`，不要从远端地址或 UA 猜测身份，不要把原始密钥混入会话 ID。显式字段仍按现有顺序解析，跨 profile 仍由服务端 scope 决定。
- [ ] **步骤 4：转绿、提交、双审。** 重跑 `scripts/run_tests.sh` 的 `tests/gateway/test_message_api.py tests/gateway/test_api_server.py tests/gateway/test_message_api_keys.py` 三文件，预期零失败；运行 `git diff --check`；只提交该两文件。执行独立规格审查与代码质量审查，记录真实 SHA 与测试计数；没有双审 PASS 不进入任务 3。

### 任务 3：恢复节点间发送与工作区 direct 模式

**文件：** 创建或修改 `tools/hermes_message_tool.py`、`tests/tools/test_hermes_message_tool.py`；修改 `gateway/platforms/message_api.py`、`gateway/platforms/api_server.py`、`tests/gateway/test_message_api.py`。

- [ ] **步骤 1：核对上游。** 运行 `rg -n 'peer dm|send_hermes_message|message_api' tools hermes_cli tests/tools`，对照 `git show main:tools/hermes_message_tool.py`。仅在上游现有 peer 工具不能发送原 `/message` 的 `command`、`api_key`、`exec_token`、`session_id` 字段时恢复 fork 的注册和 handler；测试 mock URL opener 断言目标路径为 `/message`、禁止双目标、超时和响应大小上限。不要把密钥写进日志或 schema。
- [ ] **步骤 2：红测 direct。** 把原主工作区 `git diff -- gateway/platforms/api_server.py tests/gateway/test_api_server.py` 中 `agent_mode` 的行为测试**手工移植**到新文件，确保 `agent_mode=direct` 传入 `_run_agent`，创建 Agent 时 `enabled_toolsets=[]`、`max_iterations=1`、`skip_context_files=True`、`skip_memory=True`、`skip_background_review=True`，无效值 400；`default` 不变。
- [ ] **步骤 3：确认红，最小实现。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/gateway/test_message_api.py tests/tools/test_hermes_message_tool.py'`；预期 direct/工具契约失败。按任务 2 的 mixin/method 结构传递 `agent_mode`，只为 direct 修改 Agent 构造参数，不改变其他 API 端点。`direct` 不写共享记忆笔记。
- [ ] **步骤 4：转绿并提交。** 运行上述完整测试，预期零失败；`git diff --check` exit 0。提交本任务实际修改的明确文件，消息 `feat(message): preserve peer transport and direct mode`；不得 `git add -A`。

### 任务 4：Dashboard 管理路由

**文件：** 创建 `hermes_cli/web_routers/message_keys.py`、`tests/hermes_cli/test_web_message_keys.py`；修改 `hermes_cli/web_server.py`。

- [ ] **步骤 1：红测。** 用 FastAPI TestClient 和临时 `HERMES_HOME` 请求 `GET /api/message/keys`、`POST /api/message/keys`、`DELETE /api/message/keys/{id}`、`GET /api/message/keys/policy`、`PUT /api/message/keys/policy`，沿用现有 dashboard 会话鉴权门禁；未认证必须拒绝。创建只在响应中返回一次明文；列表无明文；撤销后 `validate_key` 失败；在不同 profile 作用域下同名 key 不串号。`PUT policy` 接收 JSON `{"require_chat_key":true}`，返回新值并可被另一进程立即读取；切回 false 不影响已有密钥或 YAML。
- [ ] **步骤 2：确认红。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/hermes_cli/test_web_message_keys.py'`；预期 404/模块缺失。
- [ ] **步骤 3：实现管理端。** 新建 `router = APIRouter()`，五个方法通过已有 `_profile_scope(profile)`（跨线程 I/O 用 `scoped_to_thread`）调用任务 1 的 `list_keys/create_key/revoke_key/get_policy/set_policy`；创建入参只含 `name`，删除只接受路径 ID，policy 的值必须是布尔值；失败使用统一 `http_failure`，响应头设 `Cache-Control: no-store`。在 `web_server.py` 的 SPA catch-all 前 `include_router`。确认无 profile 时绑定当前主页，profile 不存在时沿现有 profile scope fail-closed。
- [ ] **步骤 4：转绿并提交。** 运行步骤 2 的完整测试及 `tests/hermes_cli/test_web_server.py`；预期零失败；`git diff --check` exit 0。提交 `git add hermes_cli/web_routers/message_keys.py hermes_cli/web_server.py tests/hermes_cli/test_web_message_keys.py`；`git commit -m "feat(dashboard): manage message-only keys"`。

### 任务 5：Desktop JSON-RPC 管理端

**文件：** 创建 `tui_gateway/contracts/message_keys.py`、`tui_gateway/methods_message_keys.py`、`tests/tui_gateway/test_message_keys.py`；修改 `tui_gateway/contracts/__init__.py`、`tui_gateway/server.py`、生成的 `apps/shared/src/gateway-contract.generated.ts`、`apps/shared/src/gateway-contract.openrpc.json`。

- [ ] **步骤 1：红测与契约。** 契约新增 `message.keys.list`、`message.keys.create`、`message.keys.revoke`、`message.keys.policy`、`message.keys.policy.set`：所有 `Params` 都继承 `ProfileParams`；创建额外有 `name: str`，撤销有 `id: str`，policy.set 有 `require_chat_key: bool`；列表只返回元数据，创建额外返回 `key`，撤销返回 `removed: bool`，policy.set 返回开关值，无 `restart_required`。在 `tests/tui_gateway/test_message_keys.py` 使用真实 RPC dispatcher 测试目标 profile 生效、另一 profile 不可见、未认证连接被拒及明文仅在创建结果出现。
- [ ] **步骤 2：确认红。** 运行 `bash -lc 'HERMES_PYTHON=$(command -v python) scripts/run_tests.sh tests/tui_gateway/test_message_keys.py tests/tui_gateway/contracts/test_generated.py'`；预期未注册方法/生成契约过期。
- [ ] **步骤 3：实现 RPC。** 仿 `methods_vault.py` 使用 `HandlerRegistry`、`@method(...)`、`@_profile_scoped` 和 `_ok/_err` 返回；调用任务 1 的五个服务函数。把模块加入 `server.py` 的 import 与 register 表，契约加入 `contracts/__init__.py`，执行 `python scripts/gen_gateway_contracts.py` 生成 TS/OpenRPC，禁止手工编辑生成文件。新方法不能通过无认证/未授权的 websocket 访问；确认现有 `rpc_dispatch` 与连接认证链路是否保护管理 RPC，若未保护必须在 handler 前按当前 transport 的管理员身份拒绝，而不是只相信传入的 `profile`。
- [ ] **步骤 4：转绿并提交。** 运行步骤 2 的完整测试、`python scripts/gen_gateway_contracts.py --check`（若生成器没有 `--check`，重跑生成器并用 `git diff` 验证稳定），`git diff --check`；预期零失败。提交上面列出的契约/handler/生成产物与测试，消息 `feat(desktop): expose message key management RPC`。

### 任务 6：Dashboard 与 Desktop 的密钥界面

**文件：** 创建 `web/src/components/MessageKeysPanel.tsx`、`web/src/components/MessageKeysPanel.test.tsx`、`apps/desktop/src/app/settings/message-keys-settings.tsx`、对应 `.test.tsx`；修改 `web/src/pages/EnvPage.tsx`、`web/src/lib/api.ts`、`web/src/i18n/{types,en,zh}.ts`、`apps/desktop/src/app/settings/{keys-settings,index}.tsx`、`apps/desktop/src/i18n/{types,en,zh}.ts`。

- [ ] **步骤 1：红测组件。** Dashboard 测试 mock 三个 API 调用：创建后一次性显示并复制；刷新列表时不回显；撤销需确认并刷新；请求失败显示重试。Desktop 测试 mock `requestGatewayForAgent(connectionId, profile, method, params)`：切换 profile 时列表随之切换，创建/撤销只作用于目标 profile，不把明文写入 config cache/localStorage。
- [ ] **步骤 2：确认红。** 运行 `npm test --workspace web -- src/components/MessageKeysPanel.test.tsx` 与 `npm test --workspace hermes -- src/app/settings/message-keys-settings.test.tsx`；预期新增测试失败，而非依赖缺失。依赖不可用时先 `npm ci`，不要改锁文件。
- [ ] **步骤 3：实现界面。** Dashboard 将面板嵌进既有 `/env` Keys 页并复用页面鉴权；`api.ts` 封装列表/创建/撤销/开关读取与修改，且只把一次性 `key` 放在创建响应内。Desktop 把新的 `message` 子视图加入 `KEYS_VIEWS` 与设置导航，使用生成的 RPC 类型和现有 `SettingsProfileScope`。两端可切换 `require_chat_key`，成功后刷新当前状态并提示“已即时生效，无需重启 Gateway”；不在列表/通知/错误中回显秘密。中文、英文同步写入各自类型与文案。
- [ ] **步骤 4：转绿与构建。** 运行两端组件测试、`npm run typecheck --workspace web`、`npm run typecheck --workspace hermes`、`npm run build --workspace web`、`npm run build --workspace hermes`；预期全部 exit 0。提交本任务列出的文件，消息 `feat(ui): manage message-only keys on dashboard and desktop`。

### 任务 7：状态开关、文档及完整验收

**文件：** 修改 `website/docs/user-guide/features/api-server.md`、`docs/integration/2026-09-25/upstream-port-plan.md`；补任务 2/4/5/6 已建测试中的 SQLite 状态场景，**不改** `hermes_cli/config_defaults.py` 或现有 `config.yaml` 结构。

- [ ] **步骤 1：状态回归。** 测 `require_chat_key` 在缺省/false 为无密钥聊天可用，true 无密钥 401；管理两端不得写入 `config.yaml`、不得把明文密钥放入配置导出；旧 `message_api.api_keys` 和管理员 Bearer 在开关 true 时仍能聊天，专用通话密钥不能执行命令，关闭旧命令开关后即使拥有管理员 Bearer 也不能执行显式命令。更改开关后**复用同一 Gateway adapter** 实测立即生效，UI 不应提示重启；损坏/不可读密钥库必须 fail-closed。
- [ ] **步骤 2：完整验证。** 使用 `scripts/run_tests.sh` 运行 `tests/gateway/test_message_api.py tests/gateway/test_message_api_keys.py tests/gateway/test_api_server.py tests/gateway/test_api_server_bind_guard.py tests/gateway/test_qqbot.py tests/hermes_cli/test_web_message_keys.py tests/tui_gateway/test_message_keys.py tests/tui_gateway/contracts/test_generated.py`；同跑两套前端组件测试/typecheck/build、`python -m compileall -q gateway hermes_cli tui_gateway`、`git diff --check`。若完整网关测试含已确认的上游 Windows 两项基线失败，将其与未修改 `upstream/main` 的同一测试对照报告，不归零其他失败。
- [ ] **步骤 3：双向审查。** 用 `git diff --stat upstream/main..HEAD` 和 `git diff --name-status main..HEAD` 对照上游和 fork；确认 `gateway/platforms/api_server.py`、原 `main` 未提交的 `agent_mode` 及 `package-lock.json` 都没有被隔离分支覆盖。使用 requesting-code-review 对权限、路径/资料泄露、并发状态和前端 profile 传递做独立复核；Critical/Important 问题修复后重跑步骤 2。
- [ ] **步骤 4：更新报告并提交。** 将通过/失败/跳过及环境限制和两个目标写入集成报告；`git diff --check` 后提交文档。**本步骤不合入 `main`、不推送、不部署**；整体上游合并须在其他子项目也通过后单独执行。
