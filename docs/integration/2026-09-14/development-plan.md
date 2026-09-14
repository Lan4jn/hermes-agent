# 个性化兼容迁移开发计划

> 使用 systematic debugging、TDD 和 verification-before-completion。先阅读同目录 spec.md 与 code-differences.md；按任务执行，每项独立提交。当前开发目标是让已同步候选通过现有个性化契约，最终尽量完整接纳上游，不损失已有功能。

## 任务 1：认证与凭据池 P0
文件：hermes_cli/auth.py、agent/credential_pool.py、agent/auxiliary_client.py、hermes_cli/runtime_provider.py。
- [ ] 在候选执行 python -m pytest tests/agent/test_gemini_endpoints.py tests/tools/test_hermes_message_tool.py -q --tb=short -x，确认当前 missing SINGLE_USE_REFRESH_POOL_PROVIDERS。
- [ ] 用 git show bc86ff6c4a:hermes_cli/auth.py 与 git diff fce30d818e fd4173aa1f -- hermes_cli/auth.py 分别读取上游接口和本地补丁。追踪新凭据池的全部 auth imports/callers，不能仅添加空常量让 import 通过。
- [ ] 以上游 provider/credential 生命周期为结构，迁移本地 Gemini endpoint、relogin replacement、串行 pool upsert 和脱敏行为；复用已有 helper。
- [ ] 运行 tests/agent/test_credential_pool.py、tests/agent/test_gemini_endpoints.py、tests/agent/test_gemini_cloudcode.py、tests/hermes_cli/test_runtime_provider_resolution.py、tests/hermes_cli/test_auth_commands.py；目录不存在时用 git ls-files tests 定位上游重命名，不能删掉测试。
- [ ] 验证临时 HERMES_HOME 中默认/次级 profile 使用各自 base URL 和 key_env；重新登录替换旧 token；异常无 secret。
- [ ] 提交修复与回归测试，再确认任务起始命令不再 setup error。

## 任务 2：Gateway、/message 与 QQBot P0
文件：gateway/run.py、gateway/platforms/api_server.py、base.py、qqbot/adapter.py、tools/url_safety.py、tools/hermes_message_tool.py。
- [ ] 对照上游与本地差异，列举 base adapter 的新方法签名、审批授权、取消和 dedup helper；以新版共同接口移植 QQBot 定制。
- [ ] 保留 /message 既有 JSON/鉴权/命令执行契约，按上游新 profile 路由绑定，拒绝跨 profile 访问凭据。
- [ ] 运行 tests/gateway/test_api_server.py、test_api_server_toolset.py、test_qqbot.py 与 tests/tools/test_hermes_message_tool.py、test_url_safety.py；包含匿名聊天、命令需认证、错误 key、两轮上下文和文件敏感路径测试。
- [ ] fake-IP 正常官方 API 可达，同时私网 URL、DNS rebinding、重定向到敏感目标按现有安全规则处理。
- [ ] 通过后提交，不用整文件 ours/theirs 替代此阶段。

## 任务 3：模型向导、CLI 和依赖 P1
文件：hermes_cli/model_setup_flows.py、commands.py、models.py、main.py、logout.py、cli.py、config_defaults.py、pyproject.toml、uv.lock。
- [ ] 对照新上游模型选择器与本地 Google 交互向导，统一 provider ID、api_mode、reasoning effort、base URL、重新登录和退出入口。
- [ ] 运行 tests/hermes_cli/test_model_provider_persistence.py、test_gemini_provider.py、test_gquota_command.py 与命令注册测试。
- [ ] 合并依赖声明后运行 uv lock --check；若不一致用 uv lock 生成并审查，不保留混合文本锁。uv sync --frozen 在隔离 venv 安装，不能刷新生产 venv。
- [ ] 核对 pyproject 与 hermes_cli/__init__.py 版本，明确 fork build 标识；运行 python -m compileall -q agent gateway hermes_cli tools cli.py。
- [ ] 相关测试通过后提交。

## 任务 4：Antigravity 与统一管理器功能链
- [ ] 原 Antigravity worktree 的 base.py dirty diff 先由所有者确认并备份；不自动丢弃或复制到集成分支。
- [ ] 在认证/Gateway稳定后，分别模拟合并 feature/antigravity-backend、feature/hermes-manager，审查依赖和重叠提交；按历史合并或保留作者 cherry-pick，不重新实现整套功能。
- [ ] Antigravity 验证 request timeout 传播、有效活动续期、真实超过120秒任务、stop、restart/resume、媒体、失败不重放和进程树清理。
- [ ] fleet 验证节点身份、远程配置/服务控制、认证/CORS、共享 notes、安全降级和两节点互通；multiplex 的本机 profile 不当成不同机器节点。
- [ ] 各功能独立提交与报告，任何缺口标记 NO-GO。

## 任务 5：上游回归与发布
- [ ] 在隔离环境运行 provider、Gateway、QQBot、CLI/TUI、SessionDB 和 Windows 子进程相关测试；记录命令、版本、退出码和失败节点。
- [ ] 新失败写最小 reproduction；疑似基线在固定上游或本地父提交的独立 worktree 复现，不能把所有失败标为环境问题。
- [ ] 对发生 TS 变更的 workspace 用仓库 package.json 中现存 scripts 做 typecheck/test/build，保持依赖按 workspace 安装。
- [ ] 先 Windows 本地真实模型、QQBot文件图片、/message和后台重启验收，再130 user systemd灰度。ssh 130 仅为现有别名；实际账号/路径从 systemctl --user show hermes-gateway.service 和服务启动命令读取。
- [ ] 部署前备份源目录、配置和 SQLite online backup，记录完整 SHA/runtime 路径；禁止移动runtime后声称空备份可启动。回滚必须包含可启动的旧runtime与旧源码。
- [ ] 配置升级要核对上游 multiplex 自动迁移，保护现有 user service、端口和profile边界。任何用户配置改动单独记录。
- [ ] 全部门禁通过才合回 main 并推送 fork；不创建 PR。当前集成候选不直接部署。

## 最终产物
更新 code-differences.md，逐条标记：已迁移、上游等价覆盖（附测试）、暂保留（附原因）、未完成。最终报告列出 release SHA、上游 SHA、各功能分支纳入范围、全部真实验收、基线失败和回滚位置。
完成声明必须以个性化功能通过为前提，不能仅依据 git merge 无冲突或 compileall 通过。
