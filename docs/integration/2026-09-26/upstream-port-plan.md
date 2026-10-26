# 2026-09-26 移植与定制保全分阶段实施计划 (Execution Plan)

## 阶段概览与目标

- **Phase 1: 修复编译与构建阻断 (Web & Desktop 构建/类型检查/汉化)**
  - 修复 `MessageKeysSection.tsx` 属性契约与 Web 正式 build；
  - 修复 `message-keys-setting.tsx` 属性契约与 Desktop typecheck；
  - 补齐 WebUI 与 Desktop Message Keys 的中英文多语言词条与测试。
- **Phase 2: `send_hermes_message` 工具发现与接入修复**
  - 在 `toolsets.py` 注册 `peer_messaging` 工具集与 `hermes-api-server` 默认包含；
  - 编写发现与权限测试用例，验证 API Server 运行时可以正确载入该工具。
- **Phase 3: 移植 Google Gemini CLI OAuth 与反代子系统**
  - 移植 `gemini_endpoints.py`、`google_oauth.py`、`google_code_assist.py`、`gemini_cloudcode_adapter.py`；
  - 在 `hermes_cli/auth.py` 和 `model_setup_flows.py` 恢复接入入口；
  - 运行 `test_gemini_endpoints.py` 和 `test_gemini_cloudcode.py` 确保 100% 绿灯。
- **Phase 4: QQBot 平台高级特性与安全穿透保全**
  - 移植 `gateway/platforms/qqbot/adapter.py` 的文件/图片审阅与原生审批按钮；
  - 移植 `tools/url_safety.py` 的 fake-ip 兼容逻辑；
  - 运行 `test_qqbot.py` 与 `test_url_safety.py` 验证行为一致性。
- **Phase 5: 全量回归、文档与 GO/NO-GO 决策交付**
  - 全套 Python 并行测试运行；
  - Web 与 Desktop 正式构建与测试验证；
  - 输出包含各关键提交 SHA 的最终交付报告。

---

## 阶段执行细则与 TDD 检查点

### Phase 1: Web & Desktop 构建与汉化修复
1. **Red**: 运行 `node scripts/build/web.mjs` 和 `npx tsc -p apps/desktop/tsconfig.json --noEmit`，捕获真实的 TS 报错。
2. **Green**:
   - `web/src/pages/Config/components/MessageKeysSection.tsx`: 修正 `Button` 和 `ConfirmDialog` 属性；
   - `web/src/i18n/zh.ts` 和 `en.ts`: 新增 `messageKeys` 命名空间及其翻译；
   - `apps/desktop/src/app/settings/message-keys-setting.tsx`: 修正 `notify/notifyError({ title, description })`、`ListRow description`、`ConfirmDialog destructive`；
   - 更新组件单元测试。
3. **Refactor & Verify**: 重新执行正式构建与类型检查，确认 Exit Code 均为 0。

### Phase 2: `send_hermes_message` 工具接入
1. **Red**: 编写测试 `tests/gateway/test_api_server_toolset.py`，断言 `hermes-api-server` 默认工具集包含 `send_hermes_message`。
2. **Green**: 在 `toolsets.py` 中将 `send_hermes_message` 加入 `_HERMES_CORE_TOOLS`、`peer_messaging` 和 `hermes-api-server`。
3. **Verify**: 运行测试确保断言通过。

### Phase 3: Gemini OAuth 与反代子系统
1. **Red**: 引入 `tests/agent/test_gemini_endpoints.py`，确认测试红灯（找不到模块）。
2. **Green**:
   - 移植 `agent/gemini_endpoints.py`、`agent/google_oauth.py`、`agent/google_code_assist.py`、`agent/gemini_cloudcode_adapter.py`；
   - 连接 `hermes_cli/auth.py` 和 `hermes_cli/model_setup_flows.py`；
   - 引入并运行 `tests/agent/test_gemini_endpoints.py` 和 `tests/agent/test_gemini_cloudcode.py`。
3. **Verify**: 所有 Gemini 相关测试转绿。

### Phase 4: QQBot 平台保全
1. **Red**: 针对 QQBot approval buttons 和多媒体消息编写或运行测试。
2. **Green**:
   - 将 `gateway/platforms/qqbot/adapter.py` 和 `tools/url_safety.py` 的定制补丁移植到候选分支；
   - 运行 `tests/gateway/test_qqbot.py` 和 `tests/tools/test_url_safety.py`。
3. **Verify**: 确保全部用例通过。

### Phase 5: 全量回归与交付
- 运行完整测试矩阵；
- 检查 `git status` 确保工作树纯净无遗留；
- 出具严格客观的最终报告。
