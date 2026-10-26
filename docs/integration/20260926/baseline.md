# 上游集成基线与快照冻结报告 (2026-09-26 Final Review)

## 1. 快照与环境信息

| 标识 | 引用 / SHA | 说明 |
| :--- | :--- | :--- |
| **Upstream 目标冻结快照** | `d0288be5b3330d2442e3907185b8e9d0958297bb` | 上游最新目标提交 (`snapshot/upstream-d0288be5`) |
| **Fork Main 快照基线** | `47316a9d1b6e830c01db488c65e51c6b8be55415` | 本地 `main` 分支基线 (`snapshot/fork-origin-main`) |
| **共同祖先 (Merge Base)** | `bc86ff6c4ac8785016d0023f37ad8b119ed120de` | Fork 与 Upstream 的共同祖先提交 |
| **隔离合并分支** | `codex/integration-final-20260926` | 从 `main` (`47316a9d1b`) 检出的干净合流分支 |
| **代码验收锚点** | `a2af172a690b3ce590498f567adbc3e0f285c15e` | 文档提交会改变 HEAD；实际交付提交以 `git rev-parse HEAD` 的回执为准 |
| **现有发布保护 Tag** | `release/codex-integration-final-20260926` | 保护合流验证节点 (指向 `7431defa07`，遵照规范保持原样不移动) |
| **隔离工作树目录** | `C:\Users\qwe57\.codex\worktrees\upstream-sync-20260925\hermes-agent` | 严格隔离工作树，主仓库 `F:\Documents\Project\hermes-agent` 零污染 |

## 2. 集成演进与差异处置概况

- **本地演进**：从共同祖先 `bc86ff6c4a` 到 `main` (`47316a9d1b`)，涉及 43 个定制提交。
- **上游演进**：从共同祖先 `bc86ff6c4a` 到上游快照 (`d0288be5b3`)，涉及 309 个提交。
- **合并与冲突**：执行 `git merge --no-commit --no-ff` 产生的 46 个冲突文件已全部在真实测试验证下分类消解。
- **锁文件治理 (S6)**：彻底消除手写标记，通过官方 `uv lock --check` 原生验证通过。
- **格式与严格差异 (R2)**：`git diff --check main..HEAD` 真实退出码为 0，消除了所有尾随空白与测试用例整行冲突标记。

## 3. 全链路测试与构建回执汇总 (真实退出码)

- **Web 工作区检查 (`npm run check --workspace web`)**：`EXIT_CODE=0` (typecheck 0 错误, 53 test files / 366 passed, eslint 0 错误 0 any)
- **Web 工作区生产构建 (`npm run build --workspace web`)**：`EXIT_CODE=0` (2253 模块编译完成，产物正常生成，耗时 2.76s)
- **Desktop 类型检查 (`npm run typecheck --workspace apps/desktop`)**：`EXIT_CODE=0` (4 套 TS 检查 0 错误)
- **Desktop UI 测试 (`npm run test:ui --workspace apps/desktop -- src/app/settings`)**：`EXIT_CODE=0` (53 test files / 410 passed, 0 failed, 耗时 58s)
- **Desktop 生产构建 (`npm run build --workspace apps/desktop`)**：`EXIT_CODE=0` (17430 模块转换完成，`electron-main.mjs`, `electron-preload.js` 产物已验证)
- **网关契约生成器 (`python scripts/gen_gateway_contracts.py --check`)**：`EXIT_CODE=0`
- **依赖锁文件一致性 (`uv lock --check`)**：`EXIT_CODE=0` (Resolved 331 packages in 1.11s)
- **Python 核心套件并行回归 (`scripts/run_tests_parallel.py`)**：`EXIT_CODE=0` (11 files, 809 passed, 0 failed, 4 skipped: 1 macos, 3 posix, 耗时 41.8s)
- **分支格式严格比对 (`git diff --check main..HEAD`)**：`EXIT_CODE=0` (零未决标记，零空格告警)
- **未合并文件检查 (`git ls-files -u`)**：`EXIT_CODE=0` (输出为空)
