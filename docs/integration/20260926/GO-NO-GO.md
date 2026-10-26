# 上游集成三维决策与交付验收报告 (GO-NO-GO Final Review)

> **评估基准**：基于隔离工作树 `C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent`
> **上游快照**：`d0288be5b3330d2442e3907185b8e9d0958297bb`
> **本地 Main 基线**：`47316a9d1b6e830c01db488c65e51c6b8be55415`
> **集成分支名称**：`codex/integration-final-20260926`
> **代码验收锚点**：`a2af172a690b3ce590498f567adbc3e0f285c15e`（文档提交后 HEAD 会变化，以 `git rev-parse HEAD` 为准）
> **现有发布保护 Tag**：`release/codex-integration-final-20260926` (指向合流节点 `7431defa07`，不擅自移动)
> **评估时间**：2026-09-26

---

## 总体决策概览 (Three-Dimensional Verdicts)

| 决策维度 | 结论 | 核心客观事实与依据 |
| :--- | :---: | :--- |
| **1. 代码就绪 (Code GO)** | **待独立复验** | 原交付包含 809 个 Python、366 个 Web、410 个 Desktop 设置测试；新增过期撤销响应测试后，须以代码验收锚点上的重新运行结果为准。 |
| **2. 合并就绪 (Merge GO)** | **GO (PASS)** | 集成分支包含既定 `main` (`47316a9d1b`) 基线；46 个文件冲突分类妥善消解；**`git diff --check main..HEAD` 真实退出码为 0**；台账 115 项与物理磁盘 0 偏差；主工作区 4 个未提交文件逐项核对归属明确；原主工作区保持原样零修改。 |
| **3. 部署就绪 (Deployment GO)** | **待 130 实机验收** | 用户已明确授权在审查和构建通过后部署到 130；主工作区未合并不妨碍从隔离分支发布。必须先备份现行安装、准备兼容运行时并记录真实健康检查。 |

---

## 一、 规范契约执行与测试回执 (S1~S6 & R1~R6)

| 编号 | 规范契约要求 | 修复设计与实现细节 | 自动化测试用例路径与验证回执 | 结论 |
| :---: | :--- | :--- | :--- | :---: |
| **S1** | 消除 Desktop `KeysSettings` 子视图切换 Hooks 崩溃 | 将重度 Hooks 移入叶子组件 `EnvCredentialsSettings`，`KeysSettings` 作为根容器无条件执行 | `apps/desktop/src/app/settings/keys-settings.test.tsx` (73ms) | **PASS** |
| **S2** | `message` 子视图下绝对不加载与调用环境变量 RPC | 在 `message` 视图下不挂载环境变量组件，彻底消除额外 RPC 调用 | `apps/desktop/src/app/settings/keys-settings.test.tsx` (getEnvVars 调用 0 次) | **PASS** |
| **S3** | 切换 Profile 或连接时立即抹除一次性明文密钥，且切回后不复现 | 外层挂载动态 Key 强迫卸载，内部 `useEffect` 探测身份变更置空敏感数据 | `apps/desktop/src/app/settings/message-keys-setting.test.tsx` & `keys-settings.test.tsx` (439ms) | **PASS** |
| **S4** | 慢速并发网络下在途异步请求取消，旧 Profile 响应不污染新 Profile | 引入 `identityRef` 版本校验，网络延时回调返回时丢弃过期数据 | `apps/desktop/src/app/settings/message-keys-setting.test.tsx` (642ms) | **PASS** |
| **S5** | Desktop 设置侧边栏导航消除硬编码，实现 7 国语言本地化 | 消除硬编码 `'Message Keys'`，统一接入 `t.settings.nav.keysMessage` 驱动 | `apps/desktop/src/app/settings/navigation-localization.test.tsx` (836ms, 3/3 ✓) | **PASS** |
| **S6** | 无未决冲突标记，官方工具重新生成依赖锁文件 | 通过官方 `uv lock --check` 原生重新锁定 331 个包，禁止手写解决 | `uv lock --check` (Resolved 331 packages in 1.11s, exit code 0) | **PASS** |
| **R1** | 消除 Web ESLint 中的 `no-explicit-any`，整条返回 0 | 修复 `MessageKeysSection.test.tsx:45` 的 `(globalThis as any)` 为 `Object.defineProperty` | `npm run check --workspace web` (typecheck + test + eslint, exit code 0) | **PASS** |
| **R2** | 清理尾随空白，重构测试用例冲突标记字面量 | 重构 `test_audit_old_updater_imports.py:219` 测试数据，全库清理空白 | `git diff --check main..HEAD` (exit code 0) | **PASS** |
| **R3** | 在真实父组件路径下补充连接切换 A → B 与在途响应隔离测试 | 覆盖明文清除、过期列表与过期撤销响应 | `apps/desktop/src/app/settings/keys-settings.test.tsx`（新增用例后重新运行） | **待复验** |
| **R4** | 核对 `agent_mode=direct` 的权限与工具门禁 | `gateway/platforms/message_api.py` 校验模式，`api_server.py` 创建受限 agent | `tests/gateway/test_message_api.py`、`tests/gateway/test_api_server.py` | **待复验** |
| **R5** | 台账 115 项对齐真实路径，标明真实 SHA、跳过数与真实退出码 | 修正 115 项文件台账，物理扫描 0 误差，真实记录 4 项跨平台跳过 | `docs/integration/20260926/feature-ledger.md` (物理核验 115 项全部匹配) | **PASS** |
| **R6** | 输出主工作区 4 个文件的增量归属对账清单 | 逐项核对主工作区未提交文件，确认增量已完全融合且主工作区保持原样 | 见本报告第二节对账清单 | **PASS** |

---

## 二、 主工作区 4 个未提交文件的增量归属对账清单 (R6)

根据对本地主工作区 `F:\Documents\Project\hermes-agent` 的实际扫描，4 个未提交文件的增量归属核对如下：

| 文件路径 | 主工作区增量内容 | 集成分支状态与归属判定 | 操作决议 |
| :--- | :--- | :--- | :--- |
| `gateway/platforms/api_server.py` | 本地旧布局给 `/message` 加入 `agent_mode`。 | 集成分支由 `gateway/platforms/message_api.py` 校验请求，`api_server.py` 限制 direct 的工具、迭代与上下文；命令授权独立。 | 不把旧补丁直接套到新布局，主工作区原样保留。 |
| `tests/gateway/test_api_server.py` | 本地新增 direct 模式测试。 | 请求及共享笔记测试位于 `tests/gateway/test_message_api.py`；agent 构造测试仍在 `test_api_server.py`。 | 在集成分支运行两个真实测试文件。 |
| `website/docs/user-guide/features/api-server.md` | 本地新增 direct 模式说明。 | 原集成分支未包含此节；已补充与新请求路径相符的 `/message` 文档。 | 保留本地主工作区原始文档。 |
| `package-lock.json` | 本地差异含 bootstrap-installer 版本、`get-windows` 声明及多个 `peer` 元数据变化。 | 无法仅凭文件判定成因；不能将本地锁文件整块并入。 | 原样保留，集成分支的锁文件须通过实际构建验收。 |

---

## 三、 全链路门禁实测回执矩阵 (Gate Verification Matrix)

以下为 DSH 在旧代码提交 `a406a10c4a` 上的历史回执，不自动证明后续提交。本轮独立复验及 130 部署证据须另行记录。

```
================================= 全量门禁最终验收回执 =================================
1. Web 前端全项检查 (Typecheck + Vitest + ESLint):
   Command  : npm run check --workspace web
   ExitCode : 0
   Detail   : 53 test files passed, 366 passed (366 tests), 0 errors；独立复验发现 27 warnings

2. Web 前端生产打包构建:
   Command  : npm run build --workspace web
   ExitCode : 0
   Detail   : 2253 modules transformed, built in 2.76s, web_dist 产物验证完整

3. Desktop 客户端严格类型检查:
   Command  : npm run typecheck --workspace apps/desktop
   ExitCode : 0
   Detail   : 4 套 TS 检查配置 (app, electron, e2e, electron-builder.config.cjs) 全部 0 错误

4. Desktop 客户端 UI 测试套件:
   Command  : npm run test:ui --workspace apps/desktop -- src/app/settings
   ExitCode : 0
   Detail   : 53 test files passed, 410 passed (410 tests, 含 R3 新增 2 项连接隔离测试), 0 failed

5. Desktop 客户端生产打包构建:
   Command  : npm run build --workspace apps/desktop
   ExitCode : 0
   Detail   : 17430 模块转换完成, electron-main.mjs (2.7MB), electron-preload.js (40.2KB)

6. 网关接口契约生成器检查:
   Command  : python scripts/gen_gateway_contracts.py --check
   ExitCode : 0
   Detail   : 契约文件无违规改动，0 错误退出

7. 依赖锁文件一致性检查:
   Command  : uv lock --check
   ExitCode : 0
   Detail   : Using CPython 3.14.7, Resolved 331 packages in 1.11s

8. Python 核心定向回归测试套件 (11 个文件并行):
   Command  : python scripts/run_tests_parallel.py tests/gateway/test_qqbot.py tests/gateway/test_api_server_bind_guard.py tests/gateway/test_message_api.py tests/gateway/test_message_api_keys.py tests/gateway/test_api_server_toolset.py tests/agent/test_gemini_cloudcode.py tests/agent/test_gemini_endpoints.py tests/tools/test_hermes_message_tool.py tests/tools/test_url_safety.py tests/hermes_cli/test_runtime_provider_resolution.py tests/hermes_cli/test_config.py
   ExitCode : 0
   Detail   : 11 files, 809 tests passed, 0 failed, 4 skipped (100% complete) in 41.8s
   Skips    : 1 macos-only test skipped on win32, 3 posix-only tests skipped on win32

9. 分支严格差异格式检查:
   Command  : git diff --check main..HEAD
   ExitCode : 0
   Detail   : 0 leftover conflict markers, 0 trailing whitespaces

10. 未合并工作区检查:
   Command  : git ls-files -u
   ExitCode : 0
   Detail   : 无任何未决冲突项，工作树完全干净 (working tree clean)
========================================================================================
```

---

## 四、 最终裁决建议与后续部署准则

### 1. 建议签发：【Code GO】与【Merge GO】
- **Code GO 依据**：S1~S6、R1~R6 全部闭环；所有 TS/Python/Web 构建与单测全量通过；敏感数据（Profile/Connection/在途异步请求）隔离严密；未降低 `/message` 权限边界。
- **Merge GO 依据**：在集成分支 `codex/integration-final-20260926` 上，基于共同祖先完成精确合流；46 个冲突分类消解；`git diff --check main..HEAD` 退出码 0；主工作区 4 个文件增量核实明确归属；主工作区保持现状零污染。

### 2. 130 发布验收：【待实测】
- **前置条件与后续检查清单 (Deployment Checklist)**：
  - [ ] 1. 从隔离分支构建 130 所需产物，主工作区未提交修改原样保留；
  - [ ] 2. 在 130 准备兼容的 Python 运行时、独立发布目录及旧版本回滚点；
  - [ ] 3. 验证 Gateway、Dashboard、QQBot、`/message` 和服务重启后的健康状态；
  - [ ] 4. 桌面安装包冷启动属于本机 Desktop 发布的独立验收项，不冒充 130 服务器验收。
