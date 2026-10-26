# Google Gemini CLI OAuth 自定义端点实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 让 `google-gemini-cli` 的 OAuth、userinfo、Code Assist 管理请求和推理请求全部支持 profile-aware 自定义反代端点，并补齐可靠的重新登录与退出语义。

**架构：** 新建一个只负责配置解析和 URL 安全校验的不可变端点对象。OAuth、Code Assist helper 和推理 client 显式接收该对象或其中的 Code Assist base，禁止修改模块全局常量；自定义 Code Assist base 禁止回退到 Google 官方 host。

**技术栈：** Python 3.11、stdlib `urllib`、httpx、PyYAML 配置加载、pytest。

**设计规格：** `docs/superpowers/specs/2026-08-22-google-gemini-cli-custom-endpoints-design.md`

---

## 文件结构

- `agent/gemini_endpoints.py`：官方默认值、profile-aware 配置解析、URL 校验和不可变 `GeminiOAuthEndpoints`。
- `agent/google_oauth.py`：登录、code exchange、refresh、userinfo 使用解析后的 OAuth 端点。
- `agent/google_code_assist.py`：discovery、onboarding、LRO polling、quota 使用显式 Code Assist base。
- `agent/gemini_cloudcode_adapter.py`：普通与流式推理使用 client 的 Code Assist base，并传给项目发现。
- `hermes_cli/auth.py`：runtime credential 返回自定义 Code Assist base，logout 清除真实 OAuth 文件。
- `hermes_cli/model_setup_flows.py`：模型向导保留用户配置的 Code Assist base。
- `tests/agent/test_gemini_endpoints.py`：配置与安全校验测试。
- `tests/agent/test_gemini_cloudcode.py`：OAuth、Code Assist 和 inference 请求传播测试。
- `tests/hermes_cli/test_auth_commands.py`：logout/re-login 行为测试。
- `tests/hermes_cli/test_gemini_provider.py`：provider client 与自定义 base 路由测试。
- `tests/hermes_cli/test_model_provider_persistence.py`：模型向导不覆盖反代配置。

## 任务 1：实现 profile-aware 端点解析与安全校验

**文件：**
- 创建：`agent/gemini_endpoints.py`
- 创建：`tests/agent/test_gemini_endpoints.py`

- [ ] **步骤 1：编写官方默认、自定义字段和非法 URL 的失败测试**

```python
def test_defaults_match_current_google_endpoints(monkeypatch):
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    endpoints = resolve_gemini_oauth_endpoints()
    assert endpoints.oauth_authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert endpoints.oauth_token_url == "https://oauth2.googleapis.com/token"
    assert endpoints.oauth_userinfo_url == "https://www.googleapis.com/oauth2/v1/userinfo"
    assert endpoints.code_assist_base_url == "https://cloudcode-pa.googleapis.com"
    assert endpoints.custom_code_assist is False

def test_each_custom_endpoint_is_independent(monkeypatch):
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {
        "providers": {"google-gemini-cli": {
            "oauth_authorize_url": "https://proxy.test/auth",
            "oauth_token_url": "https://proxy.test/token",
            "oauth_userinfo_url": "https://proxy.test/userinfo",
            "code_assist_base_url": "https://proxy.test/codeassist/",
        }}
    })
    endpoints = resolve_gemini_oauth_endpoints()
    assert endpoints.code_assist_base_url == "https://proxy.test/codeassist"
    assert endpoints.custom_code_assist is True

@pytest.mark.parametrize("value", [
    "http://proxy.example/token",
    "https://user:pass@proxy.example/token",
    "https://proxy.example/token?q=secret",
    "https://proxy.example/token#fragment",
    "file:///tmp/token",
])
def test_unsafe_custom_endpoint_is_rejected(monkeypatch, value):
    configure("oauth_token_url", value, monkeypatch)
    with pytest.raises(GeminiEndpointConfigError, match="oauth_token_url"):
        resolve_gemini_oauth_endpoints()
```

同时测试 `http://localhost`、`127.0.0.1`、`[::1]` 允许，非 mapping 的 provider 配置回退默认，两个 `HERMES_HOME` scope 不共享解析结果。

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
python -m pytest tests/agent/test_gemini_endpoints.py -q
```

预期：FAIL，`ModuleNotFoundError: agent.gemini_endpoints`。

- [ ] **步骤 3：实现不可变端点对象和解析器**

```python
@dataclass(frozen=True)
class GeminiOAuthEndpoints:
    oauth_authorize_url: str = OFFICIAL_AUTHORIZE_URL
    oauth_token_url: str = OFFICIAL_TOKEN_URL
    oauth_userinfo_url: str = OFFICIAL_USERINFO_URL
    code_assist_base_url: str = OFFICIAL_CODE_ASSIST_BASE_URL
    custom_code_assist: bool = False

def resolve_gemini_oauth_endpoints(config: Mapping[str, Any] | None = None) -> GeminiOAuthEndpoints:
    if config is None:
        from hermes_cli.config import load_config
        config = load_config() or {}
    # providers.google-gemini-cli 字段独立解析；每个自定义 URL 经过 _validate_endpoint。
```

`_validate_endpoint(field, value)` 使用 `urlsplit`，拒绝 userinfo/query/fragment 和非 HTTP(S)，仅 loopback host 可使用 HTTP；错误信息只含字段名和安全原因。

- [ ] **步骤 4：运行测试确认通过**

运行：`python -m pytest tests/agent/test_gemini_endpoints.py -q`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/gemini_endpoints.py tests/agent/test_gemini_endpoints.py
git commit -m "feat(gemini): resolve custom OAuth endpoints"
```

## 任务 2：让 OAuth 登录、交换、刷新和 userinfo 使用自定义端点

**文件：**
- 修改：`agent/google_oauth.py`
- 修改：`tests/agent/test_gemini_cloudcode.py`
- 测试：`tests/agent/test_gemini_endpoints.py`

- [ ] **步骤 1：编写四条 OAuth 请求传播失败测试**

```python
def test_start_flow_uses_custom_authorize_url(monkeypatch):
    endpoints = custom_endpoints()
    monkeypatch.setattr(google_oauth, "resolve_gemini_oauth_endpoints", lambda: endpoints)
    url = capture_printed_authorize_url(monkeypatch)
    assert url.startswith("https://proxy.test/oauth/authorize?")

def test_exchange_and_refresh_use_custom_token_url(monkeypatch):
    endpoints = custom_endpoints()
    calls = []
    monkeypatch.setattr(google_oauth, "_post_form", lambda url, data, timeout: calls.append(url) or token_body())
    google_oauth.exchange_code("code", "verifier", "http://127.0.0.1/cb", endpoints=endpoints)
    google_oauth.refresh_access_token("refresh", endpoints=endpoints)
    assert calls == [endpoints.oauth_token_url, endpoints.oauth_token_url]

def test_userinfo_uses_custom_url(monkeypatch):
    # 捕获 urllib.request.Request.full_url，断言只在自定义 userinfo URL 后添加 alt=json。
```

另测 `get_valid_access_token()` 在过期时解析当前 profile endpoints 后刷新；错误信息不回显 URL userinfo/token。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/agent/test_gemini_cloudcode.py -k 'oauth or refresh or userinfo' -q`

预期：FAIL，自定义端点参数尚未被接受或请求仍命中官方 URL。

- [ ] **步骤 3：显式传播端点对象**

```python
def exchange_code(..., endpoints: GeminiOAuthEndpoints | None = None) -> dict[str, Any]:
    resolved = endpoints or resolve_gemini_oauth_endpoints()
    return _post_form(resolved.oauth_token_url, data, timeout)

def refresh_access_token(refresh_token: str, *, endpoints=None, timeout=...):
    resolved = endpoints or resolve_gemini_oauth_endpoints()
    return _post_form(resolved.oauth_token_url, data, timeout)
```

`start_oauth_flow()` 和 `_paste_mode_login()` 在一次 flow 开始时解析一次 endpoints，并传给 code exchange 与 `_persist_token_response()`；后者把同一 endpoints 传给 `_fetch_user_email()`。`get_valid_access_token()` 每次需要刷新时解析当前 profile endpoints。

- [ ] **步骤 4：运行 OAuth 回归**

运行：

```powershell
python -m pytest tests/agent/test_gemini_cloudcode.py -k "oauth or refresh or credential or headless" -q
python -m pytest tests/agent/test_gemini_endpoints.py -q
```

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/google_oauth.py tests/agent/test_gemini_cloudcode.py
git commit -m "feat(gemini): proxy OAuth and userinfo requests"
```

## 任务 3：让 Code Assist discovery、onboarding 和 quota 使用反代

**文件：**
- 修改：`agent/google_code_assist.py`
- 修改：`tests/agent/test_gemini_cloudcode.py`

- [ ] **步骤 1：编写 helper 全链路 URL 失败测试**

```python
def test_load_code_assist_uses_only_custom_base(monkeypatch):
    calls = capture_post_urls(monkeypatch)
    load_code_assist("token", base_url="https://proxy.test/codeassist")
    assert calls == ["https://proxy.test/codeassist/v1internal:loadCodeAssist"]

def test_onboard_and_lro_poll_use_custom_base(monkeypatch):
    calls = capture_onboarding_urls(monkeypatch)
    onboard_user("token", tier_id="free-tier", base_url="https://proxy.test/codeassist")
    assert calls[0].startswith("https://proxy.test/codeassist/v1internal:onboardUser")
    assert calls[1] == "https://proxy.test/codeassist/v1internal/operations/op-1"

def test_quota_uses_custom_base(monkeypatch):
    retrieve_user_quota("token", project_id="p", base_url="https://proxy.test/codeassist")
    assert posted_url == "https://proxy.test/codeassist/v1internal:retrieveUserQuota"
```

测试官方默认仍尝试现有 fallback hosts；自定义 base 首次失败后不得调用任一 `FALLBACK_ENDPOINTS`。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/agent/test_gemini_cloudcode.py -k 'load_code_assist or onboard or quota or project_context' -q`

预期：FAIL，helper 不接受 `base_url` 或仍使用官方常量。

- [ ] **步骤 3：为 helper 增加显式 base 参数**

```python
def load_code_assist(..., base_url: str = CODE_ASSIST_ENDPOINT) -> CodeAssistProjectInfo:
    root = base_url.rstrip("/")
    endpoints = [root] if root != CODE_ASSIST_ENDPOINT else [root, *FALLBACK_ENDPOINTS]

def resolve_project_context(..., code_assist_base_url: str = CODE_ASSIST_ENDPOINT) -> ProjectContext:
    info = load_code_assist(..., base_url=code_assist_base_url)
    # onboard_user 同样接收并使用 code_assist_base_url。
```

所有 URL 由根地址加既有固定 path 组成，LRO operation name 仍需作为相对路径处理，不能接受服务端返回绝对 URL 覆盖 proxy host。

- [ ] **步骤 4：运行 Code Assist helper 测试**

运行：`python -m pytest tests/agent/test_gemini_cloudcode.py -k 'CodeAssist or ProjectContext or Quota' -q`

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/google_code_assist.py tests/agent/test_gemini_cloudcode.py
git commit -m "feat(gemini): proxy Code Assist management requests"
```

## 任务 4：接通普通生成、流式生成、runtime 和模型向导

**文件：**
- 修改：`agent/gemini_cloudcode_adapter.py`
- 修改：`agent/agent_runtime_helpers.py`
- 修改：`hermes_cli/auth.py`
- 修改：`hermes_cli/model_setup_flows.py`
- 修改：`tests/agent/test_gemini_cloudcode.py`
- 修改：`tests/hermes_cli/test_gemini_provider.py`
- 修改：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：编写生成、流式、runtime 与 setup 失败测试**

```python
def test_client_posts_generate_and_stream_to_custom_base(monkeypatch):
    client = GeminiCloudCodeClient(base_url="https://proxy.test/codeassist")
    client.chat.completions.create(model="gemini-3-flash-preview", messages=[...])
    assert posted_url == "https://proxy.test/codeassist/v1internal:generateContent"
    list(client.chat.completions.create(model="gemini-3-flash-preview", messages=[...], stream=True))
    assert streamed_url == "https://proxy.test/codeassist/v1internal:streamGenerateContent?alt=sse"

def test_project_discovery_receives_client_custom_base(monkeypatch):
    client = GeminiCloudCodeClient(base_url="https://proxy.test/codeassist")
    client._ensure_project_context("token", "model")
    assert resolve_mock.call_args.kwargs["code_assist_base_url"] == "https://proxy.test/codeassist"

def test_runtime_credentials_return_configured_code_assist_base(monkeypatch):
    assert resolve_gemini_oauth_runtime_credentials()["base_url"] == "https://proxy.test/codeassist"

def test_model_setup_does_not_overwrite_custom_base(monkeypatch):
    _model_flow_google_gemini_cli(config_with_proxy, current_model="")
    assert saved_provider_base == "https://proxy.test/codeassist"
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```powershell
python -m pytest tests/agent/test_gemini_cloudcode.py -k "custom_base or stream" -q
python -m pytest tests/hermes_cli/test_gemini_provider.py tests/hermes_cli/test_model_provider_persistence.py -q
```

预期：FAIL，请求仍命中 `CODE_ASSIST_ENDPOINT`，runtime/setup 仍返回 marker。

- [ ] **步骤 3：让 client 使用网络 base 而非 marker**

```python
resolved = resolve_gemini_oauth_endpoints()
self.base_url = (
    resolved.code_assist_base_url
    if not base_url or base_url == MARKER_BASE_URL
    else base_url.rstrip("/")
)
```

构造器仍只因 provider id 或 `cloudcode-pa://` marker 被选中；自定义 HTTPS base 不会误路由到 OpenAI client，因为 `agent.provider == "google-gemini-cli"` 优先。生成与 streaming URL 使用 `self.base_url`。runtime credential resolver 返回 endpoint resolver 的 Code Assist base；模型向导使用同一值确认并保存，不覆盖反代。

- [ ] **步骤 4：运行推理与 provider 回归**

运行：

```powershell
python -m pytest tests/agent/test_gemini_cloudcode.py tests/hermes_cli/test_gemini_provider.py tests/hermes_cli/test_model_provider_persistence.py -q
```

预期：全部 PASS。

- [ ] **步骤 5：提交**

```bash
git add agent/gemini_cloudcode_adapter.py agent/agent_runtime_helpers.py hermes_cli/auth.py hermes_cli/model_setup_flows.py tests/agent/test_gemini_cloudcode.py tests/hermes_cli/test_gemini_provider.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "feat(gemini): route inference through custom proxy"
```

## 任务 5：修复重新登录/退出并完成端到端验证

**文件：**
- 修改：`hermes_cli/auth.py`
- 修改：`hermes_cli/auth_commands.py`
- 修改：`tests/hermes_cli/test_auth_commands.py`
- 修改：`tests/agent/test_gemini_cloudcode.py`
- 修改：`docs/superpowers/specs/2026-08-22-google-gemini-cli-custom-endpoints-design.md`（仅在实现发现契约澄清需要时）

- [ ] **步骤 1：编写 logout 和 force re-login 失败测试**

```python
def test_google_gemini_logout_clears_real_oauth_file(tmp_path, monkeypatch):
    save_google_credentials(tmp_path)
    mark_google_provider_active(tmp_path)
    auth_logout_command(SimpleNamespace(provider="google-gemini-cli"))
    assert not (tmp_path / "auth" / "google_oauth.json").exists()
    assert get_gemini_oauth_auth_status()["logged_in"] is False

def test_auth_add_forces_google_relogin(monkeypatch):
    auth_add_command(SimpleNamespace(provider="google-gemini-cli", type="oauth", label=None))
    login.assert_called_once_with(force_relogin=True)
```

测试 logout 无 auth-store entry 但真实 Google credential 文件存在时仍成功清除；重复 logout 不报错；其他 provider logout 不调用 Google clear。

- [ ] **步骤 2：运行测试确认失败**

运行：`python -m pytest tests/hermes_cli/test_auth_commands.py -k 'google or gemini' -q`

预期：FAIL，现有 logout 只清 auth store，OAuth 文件仍存在。

- [ ] **步骤 3：在 provider-specific cleanup 中清除 Google grant**

`clear_provider_auth("google-gemini-cli")` 在 auth-store 锁外调用 `agent.google_oauth.clear_credentials()`，避免嵌套不同文件锁。只要任一状态被清除就返回 true；credential 文件缺失视为幂等成功条件，不影响其他 provider。

- [ ] **步骤 4：运行完整验证**

运行：

```powershell
python -m pytest tests/agent/test_gemini_endpoints.py tests/agent/test_gemini_cloudcode.py tests/hermes_cli/test_gemini_provider.py tests/hermes_cli/test_auth_commands.py tests/hermes_cli/test_model_provider_persistence.py -q
python -m pytest tests/agent/test_gemini_native_adapter.py tests/agent/test_auxiliary_client.py -q
python -m ruff check agent/gemini_endpoints.py agent/google_oauth.py agent/google_code_assist.py agent/gemini_cloudcode_adapter.py hermes_cli/auth.py hermes_cli/model_setup_flows.py
python -m compileall -q agent/gemini_endpoints.py agent/google_oauth.py agent/google_code_assist.py agent/gemini_cloudcode_adapter.py
git diff --check
```

预期：全部退出 0；只有项目已有且与本次无关的 warning 可保留并在交付中说明。

- [ ] **步骤 5：提交**

```bash
git add hermes_cli/auth.py hermes_cli/auth_commands.py tests/hermes_cli/test_auth_commands.py tests/agent/test_gemini_cloudcode.py
git commit -m "fix(gemini): support reliable OAuth relogin"
```

## 最终审查

- [ ] 使用 `superpowers-review` 审查 `main...HEAD` 的 endpoint、token 和 profile 隔离边界。
- [ ] 确认自定义 endpoint 配置和 token 不进入日志、异常文本或测试快照。
- [ ] 确认 custom Code Assist base 失败时没有任何官方 Google Code Assist fallback 请求。
- [ ] 确认普通 `gemini` API-key/native/custom proxy provider 行为不变。
- [ ] 使用 `verification-before-completion` 重跑任务 5 的完整验证命令。
- [ ] 使用 `finishing-a-development-branch` 完成合并或保留分支。
