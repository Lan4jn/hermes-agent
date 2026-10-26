# 同步候选代码差异与兼容缺口

## 实际执行
2026-09-14 fetch 上游，目标 bc86ff6c4ac8785016d0023f37ad8b119ed120de。本地起点 fd4173aa1feb249d769e0e2c8f63bceb7b2bd1dd。
独立分支 integration/upstream-20260914，worktree .worktrees/upstream-20260914。
初次普通三方合并有 30 个冲突路径。候选采用 -X ours 保留冲突 hunk 的本地内容，接纳无冲突上游修改。这只是兼容迁移起点，不保证自动合并结果的语义。

## 实际检查结果
第一次 compileall 发现三个自动合并语法错误：gateway/platforms/qqbot/adapter.py、hermes_cli/auth.py、hermes_cli/model_setup_flows.py。
已将这三个文件完整保留为本地 main 版本以避免破坏其定制实现；这些文件的上游改动尚未迁移。
tests/cli/test_gquota_command.py 随上游目录迁移到 tests/hermes_cli/test_gquota_command.py。
再次 python -m compileall -q agent gateway hermes_cli tools cli.py：exit 0。
再次执行定制测试（-x）：1 setup error：
ImportError: cannot import name 'SINGLE_USE_REFRESH_POOL_PROVIDERS' from hermes_cli.auth
触发链 tests/conftest.py -> agent/moa_loop.py -> agent/auxiliary_client.py -> agent/credential_pool.py:29。
因此当前不能启动验收，不可发布。首次语法错误造成的 101 setup errors 已过时，不代表修正后的状态。

## 必须人工迁移
| 代码域 | 已保留内容/差异 | 可能失效行为 | 优先级 |
|---|---|---|---|
| hermes_cli/auth.py | 全文件本地版 | 新凭据池依赖缺失，阻断导入；新 provider registry 与旧 OAuth 状态不匹配 | P0 |
| agent/credential_pool.py、auxiliary_client.py、runtime_provider.py | 上游与本地 hunk 混合 | refresh 单次使用、凭据切换、profile 路由可能不一致 | P0 |
| QQBot adapter.py | 全文件本地版 | 上游 base adapter 的授权/审批/取消接口可能不兼容 | P0 |
| model_setup_flows.py | 全文件本地版 | 上游模型选择器签名与 Gemini 向导参数不一致 | P0 |
| gateway/run.py、api_server.py、base.py | 自动合并且冲突偏向本地 | /message 与 multiplex/鉴权/会话路由语义冲突 | P0 |
| tools/url_safety.py | 保留本地冲突 hunk | fake-IP 兼容可能遗漏新 SSRF 防护 | P0 |
| pyproject.toml、uv.lock、版本模块 | 保留本地冲突 hunk | 依赖锁/版本不一致，不能按新上游运行时部署 | P1 |
| system_prompt.py、toolsets.py | 混合实现 | 缓存前缀、工具可见性与平台边界 | P1 |
| cli.py、commands、main.py、logout、models | 混合注册/入口 | CLI/provider/logout 端到端行为未验证 | P1 |
| plugins/platforms/feishu/adapter.py、测试目录 | 自动合并 | 平台 API 和测试收集需回归 | P1 |

## 复核
git diff fd4173aa1f HEAD：候选相对本地的变更。
git diff bc86ff6c4a HEAD：仍保留的本地定制及未迁移上游差异。
git log main..feature/antigravity-backend 和 git log main..feature/hermes-manager：未纳入功能链。
原上游版本差异报告在主工作区 docs/reports/2026-09-14-upstream-version-feature-comparison.md。
不得把本报告的“候选合并完成”解读为“个性化功能验证完成”。
