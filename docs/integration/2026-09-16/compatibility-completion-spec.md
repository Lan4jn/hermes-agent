# Hermes 上游兼容候选完成规格

## 目标

将 `integration/upstream-20260914` 整理为可审查、可复测、可部署验收的 Hermes Agent 上游兼容候选，同时保持现有本地功能和核心运行不变量。

## 固定基线

- 工作区：`F:\Documents\Project\hermes-agent\.worktrees\upstream-20260914`
- 分支：`integration/upstream-20260914`
- 合并基线：`e144ed8cdc53e1d176ac35bc1b22e9857a06159b`
- 已纳入上游提交：`bc86ff6c4ac8785016d0023f37ad8b119ed120de`

## 功能要求

### R1：认证接口兼容

`hermes_cli.auth` 必须继续导出凭据池依赖的 OAuth grant 常量和函数。单次刷新凭据的修复、去重和通知行为必须沿用 `auth_oauth_grants` 的权威实现。

### R2：凭据状态清除可持久化

`write_credential_pool()` 与 `CredentialPool._persist()` 必须传递 `status_cleared_ids`，显式清除的 cooldown/quarantine 状态不能被磁盘旧值恢复。

### R3：Gemini 接入保持兼容

Google Gemini CLI OAuth、自定义统一反代地址、重新登录和 endpoint 解析必须继续工作。配置保存不能覆盖用户已有的默认模型。

### R4：模型与 provider 配置保持一致

模型目录 helper、provider 解析、模型选择和 ZAI endpoint 选择必须使用上游现有接口。保存 provider 配置时，只修改本次选择对应字段；已有 `model.default` 在没有明确选择新模型时保持不变。

### R5：API Server 契约完整

API Server 必须满足以下约束：

- `APIServerAdapter` 完整初始化 run、session、message、并发控制和模型恢复状态。
- `/v1/capabilities` 返回结构化 `runs_idempotency` 能力。
- `/v1/chat/completions`、`/v1/responses` 和 session chat 正确传递请求模型、provider、reasoning、service tier、relay metadata 与 session key。
- 只采用非空真实字符串作为 continuation session ID；无效 resolver 返回值必须回退原 ID。
- `/message` 默认开关、远程访问、命令执行门禁、共享 notes 和历史能力保持原有配置语义。

### R6：QQBot 文件和图片能力保持兼容

QQBot 必须保持附件、图片、文本文件读取、审批、命名 profile 会话键、私聊授权及 SSRF/fake-IP 防护。异步失败路径不得泄漏未等待协程。

### R7：运行不变量

本次集成不得破坏：

- profile 数据隔离；
- prompt cache 的稳定前缀；
- user/assistant/tool 消息顺序；
- session ID 与 gateway session key 的独立语义；
- Windows 本地后台运行所需的现有进程行为。

## 质量要求

### Q1：规定测试全部通过

以下测试必须在同一工作树、同一最终代码状态下通过：

```powershell
python -m pytest tests/gateway/test_api_server.py tests/hermes_cli/test_runtime_provider_resolution.py tests/hermes_cli/test_model_provider_persistence.py -q --tb=short
python -m pytest tests/agent/test_credential_pool.py tests/gateway/test_qqbot.py tests/agent/test_gemini_endpoints.py tests/tools/test_hermes_message_tool.py -q --tb=short
```

当前独立基线分别为 `212 passed` 和 `248 passed`。最终提交后必须重新执行，不能引用提交前结果。

### Q2：静态完整性检查通过

```powershell
python -m compileall -q agent gateway hermes_cli tools
git diff --check HEAD^ HEAD
```

### Q3：差异可审查

- 不使用空实现、宽泛 `except Exception` 或测试跳过掩盖接口不兼容。
- 不删除失败测试来获得绿色结果。
- 不覆盖工作区中不属于本次集成的用户修改。
- 每个生产修改都能对应到 R1-R7 中至少一项要求。

### Q4：形成稳定提交

完成后必须生成本地提交 SHA。提交只包含本次兼容代码、必要测试和本规格/计划，不纳入无关未跟踪文件。

## 完成判定

只有同时满足以下条件才可标记 `GO`：

1. Q1 两组测试在最终提交后全部通过。
2. Q2 静态检查通过。
3. 工作树除明确保留的历史文档外无本次未提交生产代码。
4. 提供提交 SHA、测试命令、通过数量和剩余 warning。
5. Windows 本地部署验收作为下一阶段执行，当前候选不得直接覆盖生产环境。
