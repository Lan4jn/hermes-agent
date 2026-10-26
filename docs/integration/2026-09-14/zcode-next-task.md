# ZCode 当前执行入口

唯一工作区：`F:\Documents\Project\hermes-agent\.worktrees\upstream-20260914`

当前目标：把已通过基础回归的上游兼容修改整理为可审查、可复测的本地提交候选。

最终目标：在保持认证、Gemini、API Server、`/message`、QQBot、Windows 行为、profile 隔离、prompt cache 和 session 完整性的前提下，完成上游兼容候选，并为后续本地及远程部署验收提供稳定提交 SHA。

执行依据：

- 规格：`docs/integration/2026-09-16/compatibility-completion-spec.md`
- 计划：`docs/integration/2026-09-16/upstream-integration-completion-plan.md`

按计划逐项执行。不得只更新补丁或报告；必须审查实际差异、运行规定测试、精确暂存并提交。不得合入 `main`、推送或部署。完成后提供提交 SHA 和提交后测试证据。
