# 上游同步与个性化兼容规格

## 当前开发目标
将本地 main fd4173aa1f 与上游 bc86ff6c4ac8785016d0023f37ad8b119ed120de 集成为可测试候选，逐项迁移个性化功能到上游结构。最终目标是在现有个性化功能正常使用的前提下尽量同步上游；上游祖先关系完整不等于功能同步完整。

## 范围与现状
集成分支 integration/upstream-20260914，独立 worktree。当前仅整合 main；Antigravity 与 fleet manager 两个功能分支尚未集成，原工作树和未提交修改保留。生产服务未部署。
候选处于 NO-GO：语法编译通过，但测试在认证模块导入阶段失败。

## 功能契约
1. Google CLI OAuth、用户自定义反代地址、重新登录替换凭据及错误脱敏继续可用。
2. /message 请求/回复字段、认证 token、执行命令开关、节点共享 notes 与 send_hermes_message 行为保持兼容。
3. QQBot 文本、文件、图片、fake-IP 环境下载及审批用户授权继续可用；安全边界不得因兼容而放宽。
4. Windows 本地后台运行、服务重启、子进程清理可用。
5. Antigravity 分支集成后保留持久会话、timeout 活动续期、媒体路径、安全中断及不重放命令契约。
6. fleet manager 分支集成后保留远程节点标识、配置读取/控制、鉴权和 profile liveness。
7. 上游 multiplex/profile 隔离不导致跨 profile 使用凭据、共享不应共享的会话或覆盖用户配置。
8. 新配置优先使用上游既有结构；不为单个 provider 引入第二套生命周期。
9. 不在已有对话中途改 system prompt、tool schema 或历史消息以掩盖不兼容。

## 发布条件
所有本地定制测试和相关上游测试通过；真实 Windows/130 QQBot 文件图片、/message 两轮、模型登录与推理通过；Antigravity 长任务及 stop/resume 通过；fleet 两节点互通通过。记录已知基线失败并用父提交复现，不用短 OK 或 health 200 代替完整功能验收。
只有验收通过才将集成候选合回 main、推送和部署。版本声明、依赖锁及部署标记必须一致，不能保留混合的 0.20.6/0.21.2 标识。
