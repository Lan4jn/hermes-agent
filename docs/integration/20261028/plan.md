# 2026-10-28 官方 Hermes 主线集成计划与冲突划分规范

> **面向 AI 代理的工作者：** 本文档为 2026-10-28 官方最新主线（`ee7e0f517232fb619c72e49d7e648436bddc598e`）与本地集成基准（`bb2559b48ace47e6151619f4b264da23ba889ab9`）的合并指导规范。

**目标：** 在隔离分支 `integration/upstream-20261028` 上，将官方最新提交 `ee7e0f517232` 完整合并入代码库，100% 保持既有业务定制能力、安全加固及测试基准。

**共同祖先（Merge-Base）：** `b3c28838095b0e1a43484caf642ee48b18fcee42`

---

## 一、冲突文件分类与责任边界（Scope 分工）

本次三方合并在工作树共产生 **15 个** 待解决冲突文件，按照领域职责严格划分为两组：

### 组 1：Task-24 界面与桌面端契约 Scope (`apps/`, `web/`, `website/`)
由 **task-24** 专职成员负责，后端成员不得修改：

1. `apps/desktop/electron/main.ts`：处理 OAuth 会话登录完成回调、外部链接拦截与新上游主进程事件。
2. `apps/desktop/src/app/capabilities/index.test.tsx`：能力面板测试用例合并与断言对齐。
3. `apps/desktop/src/i18n/zh-hant.ts`：繁体中文语言包增量键值同步。
4. `apps/desktop/src/i18n/zh.ts`：简体中文语言包增量键值同步。
5. `web/src/components/ModelReloadConfirm.tsx`：模型热重载确认弹窗与新组件状态对齐。
6. `web/src/i18n/zh.ts`：Web 仪表盘中文翻译条目合并。
7. `web/src/pages/ChannelsPage.tsx`：渠道配置页面上游重构与本地字段对齐。
8. `web/src/pages/SystemPage.tsx`：系统状态监控页面布局与中文化展示。
9. `website/i18n/zh-Hans/docusaurus-plugin-content-docs/current/user-guide/features/tool-gateway.md`：网关特性文档中文合并。

---

### 组 2：Task-25 Python 后端与核心服务 Scope (`agent/`, `gateway/`, `hermes_cli/`)
由 **task-25** 专职成员负责，界面成员不得修改：

1. `agent/agent_runtime_helpers.py`：保持运行时辅助函数签名与新上游调用链一致。
2. `gateway/platforms/api_server.py`：
   - 保持 `normalize_api_server_host` 支持 `dual`、`::`、`0.0.0.0` 显式绑定；
   - 保持 `_create_agent` 与 `_run_agent` 的 `agent_mode="direct"` 透传；
   - 保持 `message_api` 特性矩阵与端点过滤。
3. `hermes_cli/gateway.py`：
   - 保持网关管理命令、Windows 服务监管模式与进程生命周期控制。
4. `hermes_cli/models_catalog_static.py`：
   - 静态模型目录定义合并，保持自定义模型条目与官方最新更新共存。
5. `hermes_cli/runtime_provider.py`：
   - 保持 `looks_like_openrouter_key` 与 `resolve_gemini_oauth_runtime_credentials` 导出与解析。
6. `hermes_cli/web_server.py`：
   - 保持 `_shared_metrics_routes` 与 `_message_keys_routes` 的双向挂载。

---

## 二、定制特性保活清单（不可回退的硬性要求）

1. **Gemini 体系与多模型可配置支持**：
   - Gemini CLI OAuth 登录、刷新及 CloudCode 交互接口 (`agent/gemini_cloudcode_adapter.py`, `agent/google_code_assist.py`, `hermes_cli/auth_gemini.py`)；
   - 动态分档模型 `gemini-3.8-flash-tiered` 与思考参数适配，保持 provider resolver 通用可配置，不硬编码或绑死用户模型；
   - CLI `/gquota` 配额查询指令 (`hermes_cli/cli_commands_mixin.py`)。
2. **Message API 跨节点消息互联**：
   - `/message` 独立接口与鉴权机制 (`gateway/platforms/message_api.py`, `gateway/platforms/message_api_keys.py`)；
   - `send_hermes_message` 核心工具与 `peer_messaging` 工具集 (`tools/hermes_message_tool.py`, `toolsets.py`)，遵循上游插件化架构演进；
   - Web 控制台 Message Keys 管理路由与 UI 组件。
3. **QQBot 平台插件完备性**：
   - `plugins/platforms/qqbot/adapter.py` 内部保留通用扩展名纠偏、文本注入与超 100KB 切片预览（`Preview`）；
   - 保留按钮审批交互 (`ExecApprovalPrompt`)。
4. **运行环境与系统隔离**：
   - 彻底维护 P1-1 修复：`api_server.py` -> `session_api_turn.py` -> `run_turn_runner.py` 链路中的 `agent_mode="direct"` 单轮、空工具集强制约束；
   - 彻底维护 P1-2 修复：`runtime_provider_custom.py` 优先从传入 `config["model"]["base_url"]` 提取，严禁穿透破坏 Profile Scope；
   - Windows 平台 PM 环境导入保活机制 (`gateway/run.py::_ensure_windows_gateway_venv_imports`)。
5. **多端本地化体验**：
   - Desktop 与 Web 端完整的简繁中文翻译及配置界面。

---

## 三、用户授权发布与部署全流水线

1. **本地集成与全量测试**：
   - Task-24 与 Task-25 冲突全部解决并经由测试验证后，由独立 Reviewer（Task-26）进行代码审计；
2. **Commit 与 Push**：
   - 由 Git Owner 统一定稿 commit 并推送至 `origin/integration/upstream-20261028` 分支，杜绝推往 main 或使用 force push；
3. **Windows 与 130 生产部署**：
   - 按照正式 PM 流程生成新环境，执行 `hermes pm install`，完成网关平滑切换，验证健康检查与端到端模型调用；
4. **Mac 远程端同 SHA 安装**：
   - Mac 节点通过 Git 同步相同 Commit SHA，执行干净构建与安装，实现三端版本绝对一致；
5. **全流程安全门禁**：
   - 变更前创建 fresh backup，测试失败或部署异常时立即回滚至既有稳定状态。
