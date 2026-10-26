# Desktop 持久远程认证实现计划

> **面向 AI 代理的工作者：** 使用 executing-plans 在当前隔离工作树逐任务执行，先红后绿并记录验证。

**目标：** 一次登录后 Desktop 再启动可恢复同一 Gateway 的授权与连接。

**架构：** 复用现有连接注册表、Cookie 分区、NativeTokenSet 与 refresh coordinator；只补足持久写入成功边界。新增一个 Electron 无依赖的 Cookie 登录完成协调器，main.ts 只注入 Cookie 读取和 flushStore。

**技术栈：** Electron、TypeScript、Vitest、Node.js 文件系统与真实 Chromium WebSocket。

---

## 文件职责
- `apps/desktop/electron/native-token-store.ts`：序列化存储与明确写入失败。
- `apps/desktop/electron/native-token-store.test.ts`：磁盘错误不谎报成功、不覆盖原授权。
- `apps/desktop/electron/oauth-login-completion.ts`：Cookie 登录检测、flush 与并发完成协调。
- `apps/desktop/electron/oauth-login-completion.test.ts`：成功必须等待 flush，并发与错误契约。
- `apps/desktop/electron/main.ts`：接入真实 Cookie flush、复用 writeSecretFileAtomic 写原生秘密文件。
- `apps/desktop/electron/oauth-logout.ts` 与测试：原生退出身份栅栏先执行，Cookie 清理 finally 保证执行。
- `apps/desktop/electron/remote-auth-restart-fixture/main.ts`：真实 Electron 进程、Cookie 分区、safeStorage、Bearer/Cookie WS RPC 恢复。
- `apps/desktop/scripts/test-remote-auth-restart.mjs`：编译 fixture、启动两个独立进程、收集退出码、清理独立临时用户目录。

### 任务 1：基线与写入失败
- [x] 基线：`node ../../node_modules/vitest/vitest.mjs run --project electron electron/native-token-store.test.ts electron/oauth-partition.test.ts`；33 tests PASS。
- [x] 改写旧吞错误测试为 `assert.throws(() => persistNativeTokenSet(GATEWAY, TOKENS, disk.io), /could not be saved/)`；添加已有凭据未被失败替换验证。
- [x] 运行上述 native-token-store 测试，确认 Missing expected exception 红灯。
- [x] 写入 catch 使用固定安全错误抛出：`throw new Error('Remote login credentials could not be saved. Check Desktop storage permissions and try again.')`，不拼接异常中可能含秘密的内容。
- [x] 再次跑 native-token-store 与 refresh coordinator 回归。

### 任务 2：Cookie 登录持久完成
- [x] 测试定义 injected deps：`hasSession(): Promise<boolean>`，`flushCookies(): Promise<void>`，`onSuccess(): void`，`onFailure(error: Error): void`。
- [x] 写延迟 flush 测试，验证 flush 未完成 success=0，并发检查只 flush 一次；拒绝 flush 时 failure=1 success=0。
- [x] 实现 `createOauthLoginCompletion(deps): () => Promise<void>`，复用进行中的 Promise，成功/失败完成后不再轮询。
- [x] main.ts 用协调器替代 hasOauthSessionCookie→finish，注入 `sess.cookies.flushStore()`；原生 store 写入器替换为 `writeSecretFileAtomic`。
- [x] 运行 Cookie 协调器与完整 auth 回归，再做 Electron TypeScript 编译检查。

### 任务 3：真实进程重启
- [x] 在独立临时 userData 与 loopback 测试 Gateway 上登录；Cookie 含 Max-Age，登录完成调用生产协调器并 flush。
- [x] 关闭第一次 Electron 进程，第二次使用同一 userData，调用真实分区 Cookie 网络请求签发新 ticket，再建立 WebSocket/RPC，确认服务器仅一次登录。
- [x] 运行测试，保留退出码与覆盖范围；实际 Windows 整机重启与真实 130 登录不在自动 fixture 中声称已通过。

### 任务 4：审查与交付
- [x] 检查 `git diff --check`，确保无 secret、无跨分区复制、无 cached OAuth ticket fallback。
- [x] 跑受影响 Vitest suites、Electron 类型检查与真实 Electron fixture。
- [x] 提交源码、测试、设计、计划与证据；不 push，不覆写正在运行的用户应用。

## 验证记录（2026-10-07，Windows）
- TDD 红灯：原生写失败旧实现 Missing expected exception；Cookie 完成旧实现 flush 次数为 0；退出删除失败旧流程没有 Cookie cleanup；不可读 store 被误判为不存在时删除没有抛错。
- 最终回归：14 个 Electron suites，132 tests PASS；连接注册表 UI suite，32 tests PASS；合计 164 tests。
- Electron TypeScript noEmit PASS，受改动认证模块 ESLint max-warnings=0 PASS，main.ts ESLint quiet PASS，git diff --check PASS。
- 真实 Electron 40.10.2 Windows 进程：login EXIT=0，restore EXIT=0；第二次无登录请求、一次原生 refresh、新 ticket、真实 WebSocket RPC 两种身份路径均通过。
- 原生 fixture：预种虚构过期 Token，真实 Windows safeStorage 持久化；cookieless fetch refresh，生产 parseTokenResponse，Bearer-only ticket mint 拒绝 Cookie；Cookie fixture 使用真实 Chromium persistent 分区与 flushStore。
- 可重复命令（Desktop 目录）：`node scripts/test-remote-auth-restart.mjs <electron.exe>`。runner 自动编译并使用新的临时目录，不触碰用户会话。
- 源码审查修复：缺失原生记录删除 no-op；不可读/不可解析存储在 mutation 时拒绝而非按空存储处理（唯 ENOENT 可视为缺失）；加载仍宽容；真实写入/删除失败固定脱敏错误；Cookie logout finally 清理，原生身份栅栏保持在前。
- 首次完整 Desktop build 被 freshness 检查拒绝：构建期间整理 import 导致输入变化。交付前在源码提交后冻结输入重新构建，具体结果以最终构建退出码为准，不能把前次失败称为成功。
- 未覆盖：完整 installed Desktop startup/IPC、真实 provider PKCE 交互、真实 130 首次登录与 Windows 整机重启。未替换用户安装版、未迁移历史共享 Cookie、未更改运行中的连接/安全存储策略。
- 当前用户启动偏好为 primary=local、lastUsed=local、launchMode=primary。自动进入 kylin 需要通过现有设置选择 last-used 并成功使用 kylin，或设 kylin 为显式启动默认；不覆盖用户选择。
