# Gemini CLI 交互式反代配置实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 `hermes model` 选择 `google-gemini-cli` 时配置 Google 官方端点或一个统一反代源站，并且不影响任何其他模型或配置。

**架构：** 在现有 `hermes_cli/model_setup_flows.py` 中增加三个窄辅助函数：纯函数完成源站校验/派生和统一配置识别，持久化函数只修改用户原始 YAML 中四个 Gemini 端点字段。现有 OAuth、凭据解析和模型选择流程保持不变，只在其前方插入已确认的端点配置步骤。

**技术栈：** Python 3、`urllib.parse`、现有 CLI picker/`line_input`、PyYAML/ruamel 原子写入、pytest。

---

## 文件结构

- 修改：`hermes_cli/model_setup_flows.py`，包含统一源站辅助函数、最小配置持久化和 Gemini 专属交互接线。
- 修改：`tests/hermes_cli/test_model_provider_persistence.py`，覆盖纯函数、配置不变量、取消/非法输入和完整交互顺序。

### 任务 1：统一源站契约

**文件：**
- 修改：`hermes_cli/model_setup_flows.py`
- 测试：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：编写失败的源站派生和识别测试**

```python
def test_gemini_proxy_origin_derives_all_required_endpoints():
    assert _derive_gemini_proxy_endpoints("https://proxy.example.test/") == {
        "oauth_authorize_url": "https://proxy.example.test/o/oauth2/v2/auth",
        "oauth_token_url": "https://proxy.example.test/token",
        "oauth_userinfo_url": "https://proxy.example.test/oauth2/v1/userinfo",
        "code_assist_base_url": "https://proxy.example.test",
    }

@pytest.mark.parametrize("origin", [
    "http://remote.test", "https://user@proxy.test", "https://proxy.test/path",
    "https://proxy.test?x=1", "https://proxy.test#fragment", "ftp://proxy.test",
])
def test_gemini_proxy_origin_rejects_unsafe_or_non_origin_urls(origin):
    with pytest.raises(GeminiEndpointConfigError):
        _derive_gemini_proxy_endpoints(origin)

def test_detects_only_exact_unified_endpoint_pattern():
    assert _gemini_unified_proxy_origin(_derive_gemini_proxy_endpoints(
        "https://proxy.example.test"
    )) == "https://proxy.example.test"
    assert _gemini_unified_proxy_origin({
        "oauth_authorize_url": "https://one.test/auth",
        "oauth_token_url": "https://two.test/token",
        "oauth_userinfo_url": "https://three.test/userinfo",
        "code_assist_base_url": "https://four.test",
    }) is None
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -q`

预期：FAIL，导入 `_derive_gemini_proxy_endpoints` 失败。

- [ ] **步骤 3：编写最少纯函数实现**

```python
GEMINI_ENDPOINT_KEYS = (
    "oauth_authorize_url", "oauth_token_url",
    "oauth_userinfo_url", "code_assist_base_url",
)

def _derive_gemini_proxy_endpoints(origin: str) -> dict[str, str]:
    normalized = normalize_code_assist_base_url(origin, field="proxy_origin")
    parsed = urllib.parse.urlsplit(normalized)
    if parsed.path not in ("", "/"):
        raise GeminiEndpointConfigError("proxy_origin: must not include a path")
    origin = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
    return {
        "oauth_authorize_url": f"{origin}/o/oauth2/v2/auth",
        "oauth_token_url": f"{origin}/token",
        "oauth_userinfo_url": f"{origin}/oauth2/v1/userinfo",
        "code_assist_base_url": origin,
    }
```

`_gemini_unified_proxy_origin()` 从 `code_assist_base_url` 候选源站重新派生并要求四个字段完全相等，否则返回 `None`。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -q`

预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add hermes_cli/model_setup_flows.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "feat: validate unified Gemini proxy origins"
```

### 任务 2：四字段安全持久化

**文件：**
- 修改：`hermes_cli/model_setup_flows.py`
- 测试：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：编写失败的配置不变量测试**

```python
def test_save_gemini_endpoints_changes_only_four_provider_fields(config_home):
    before = {
        "model": {"default": "old", "provider": "openrouter"},
        "providers": {
            "openrouter": {"api_key": "keep"},
            "google-gemini-cli": {"account": "keep", "oauth_token_url": "old"},
        },
        "tools": {"keep": True},
    }
    config_path.write_text(yaml.safe_dump(before))
    _save_gemini_endpoint_overrides(_derive_gemini_proxy_endpoints("https://proxy.test"))
    saved = yaml.safe_load(config_path.read_text())
    assert saved["model"] == before["model"]
    assert saved["providers"]["openrouter"] == before["providers"]["openrouter"]
    assert saved["providers"]["google-gemini-cli"]["account"] == "keep"
    assert saved["tools"] == before["tools"]

def test_official_mode_removes_only_endpoint_fields(config_home):
    _save_gemini_endpoint_overrides(None)
    assert saved["providers"]["google-gemini-cli"] == {"account": "keep"}
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -q`

预期：FAIL，导入 `_save_gemini_endpoint_overrides` 失败。

- [ ] **步骤 3：实现原始配置原子写回**

```python
def _save_gemini_endpoint_overrides(endpoints: dict[str, str] | None) -> None:
    from hermes_cli.config import get_config_path, read_user_config_raw
    from utils import atomic_roundtrip_yaml_save

    path = get_config_path()
    config = read_user_config_raw(path)
    providers = config.setdefault("providers", {})
    provider = providers.setdefault("google-gemini-cli", {})
    for key in GEMINI_ENDPOINT_KEYS:
        provider.pop(key, None)
    if endpoints:
        provider.update(endpoints)
    atomic_roundtrip_yaml_save(path, config)
```

实现需保留非映射旧值的安全归一化，并且不得读取合并了默认值的 `load_config()` 作为写回源。

- [ ] **步骤 4：运行测试验证通过**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -q`

预期：PASS，并确认 YAML 注释保留断言通过。

- [ ] **步骤 5：Commit**

```bash
git add hermes_cli/model_setup_flows.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "feat: persist Gemini endpoint mode safely"
```

### 任务 3：接入 Gemini 专属交互流程

**文件：**
- 修改：`hermes_cli/model_setup_flows.py:895`
- 测试：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：编写失败的完整流程测试**

```python
def test_custom_proxy_confirms_saves_then_starts_oauth(config_home):
    events = []
    with patch("hermes_cli.main._prompt_provider_choice", return_value=1), \
         patch("hermes_cli.model_setup_flows.line_input", return_value="https://proxy.test"), \
         patch("hermes_cli.model_setup_flows.prompt_yes_no", return_value=True), \
         patch("agent.google_oauth.start_oauth_flow", side_effect=lambda **_: events.append("oauth")), \
         patch("hermes_cli.model_setup_flows._save_gemini_endpoint_overrides",
               side_effect=lambda value: events.append(("save", value))):
        _model_flow_google_gemini_cli(load_config(), "old")
    assert events[0][0] == "save"
    assert events[1] == "oauth"

def test_custom_proxy_cancel_or_invalid_input_does_not_write_or_login(...):
    # Picker cancel, input cancellation, invalid origin and rejected confirmation
    # each assert save and OAuth mocks were not called.

def test_official_mode_removes_overrides_before_oauth(...):
    # Official selection + confirmation calls save(None), then OAuth.

def test_independent_endpoints_are_not_silently_replaced(...):
    # Existing non-unified values produce no origin prefill and require the final
    # replacement confirmation before any write.
```

- [ ] **步骤 2：运行测试验证失败**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py -q`

预期：FAIL，因为当前流程不显示端点模式选择且直接进入 OAuth。

- [ ] **步骤 3：编写最少交互接线**

新增 `_configure_gemini_endpoints_interactively(config) -> dict | None`，返回更新后的内存配置或取消标记。它使用 `_prompt_provider_choice` 提供两个模式，custom 模式使用 `line_input` 预填统一源站，打印四个最终 URL 和 OAuth 敏感信息警告，再用 `prompt_yes_no(..., default=False)` 确认。仅确认后调用 `_save_gemini_endpoint_overrides`，并将四字段变更同步到传给现有 resolver 的内存配置。

`_model_flow_google_gemini_cli` 在检查登录状态之前调用该函数；取消立即返回。后续 OAuth、凭据解析、picker 和 `_save_model_choice` / `_update_config_for_provider` 保持原结构。

- [ ] **步骤 4：运行聚焦测试验证通过**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py tests/agent/test_gemini_endpoints.py tests/hermes_cli/test_auth_commands.py -q`

预期：PASS。

- [ ] **步骤 5：运行相关回归测试**

运行：`python -m pytest tests/test_google_oauth.py tests/test_gemini_cloudcode.py tests/test_gemini_oauth_provider.py -q`

预期：PASS；若文件名随仓库变化，以 `rg --files tests | rg 'gemini|google_oauth'` 找到现有对应套件后运行。

- [ ] **步骤 6：Commit**

```bash
git add hermes_cli/model_setup_flows.py tests/hermes_cli/test_model_provider_persistence.py
git commit -m "feat: configure Gemini proxy in model wizard"
```

### 任务 4：最终验证

**文件：**
- 验证：`hermes_cli/model_setup_flows.py`
- 验证：`tests/hermes_cli/test_model_provider_persistence.py`

- [ ] **步骤 1：运行格式和静态检查**

运行：`python -m compileall -q hermes_cli/model_setup_flows.py`

预期：退出码 0。

- [ ] **步骤 2：运行模型设置与 Gemini 全量聚焦套件**

运行：`python -m pytest tests/hermes_cli/test_model_provider_persistence.py $(rg --files tests | rg 'gemini|google_oauth') -q`

预期：全部 PASS；平台特定测试仅允许已有的明确 SKIP。

- [ ] **步骤 3：检查差异和工作树**

运行：`git diff --check && git status --short`

预期：无空白错误，只有计划内文件发生变化。

