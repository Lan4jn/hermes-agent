# Web 与 Desktop 全站中文化实施计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框跟踪进度。

**目标：** 保留英文及专有名词，补齐 `zh`/`zh-hant` 下 Web Dashboard 与 Desktop 所有第一方用户可见界面的中文，最终以可回滚的侧装冷启动版本替换 `F:\hermes-desktop`。

**架构：** 沿用 Web 的 `I18nProvider` 与 Desktop 的 `defineLocale(en, overrides)`，不新增运行时翻译系统。各页面在原有词典中定义文本，在渲染/错误处理处读取；外部接口原文、插件/技能数据不翻译。将前端代码验收与 Desktop 实际安装验收拆开。

**技术栈：** React 19、TypeScript、Vitest、Vite、Electron、electron-builder、PowerShell。设计依据：`docs/superpowers/specs/2026-09-27-web-desktop-localization-design.md`。

---

## 文件与职责

- `docs/integration/20260927/localization-ledger.md`：按 Web 页面及 Desktop 表面记录主要状态、翻译点、排除项和验收结果；只做审计证据，不供运行时代码加载。
- `web/src/i18n/en.ts`、`zh.ts`、`zh-hant.ts`、`types.ts`、`pagesEn.ts`、`pagesZh.ts`、`pagesZhHant.ts`、`pagesTypes.ts`：Web 现有静态字典，新增/修复页面文案、类型及函数参数。
- `web/src/pages/{ChannelsPage,McpPage,SkillsPage,SystemPage,ProfilesPage,ProfileBuilderPage,ModelsPage,SessionsPage,CronPage,PluginsPage,PairingPage,WebhooksPage,ConfigPage,FilesPage,LogsPage,EnvPage,AnalyticsPage,ChatPage}.tsx`：按实际页面替换第一方可见硬编码，保持接口调用及状态机不变；仅修改审计发现问题的文件。
- `web/src/pages/*.test.tsx`、`web/src/i18n/i18n.test.ts`：页面简/繁中渲染、操作/错误提示与字典键契约；新增用例放在相应页面测试中，不写扫描源码文本的测试。
- `apps/desktop/src/i18n/{en,zh,zh-hant,types,catalog-completeness.test}.ts`：Desktop 英文基准、中文覆盖与插值契约。
- `apps/desktop/src/app/{settings,chat,capabilities,contrib}`、`apps/desktop/src/components/{onboarding,update-status.tsx}`：仅修改审计确认存在英文漏译的 UI；按最近的同目录 `*.test.tsx` 添加组件行为测试。
- `apps/desktop/release/` 与 `apps/desktop/dist/`：构建产物，不手工编辑或提交。`F:\hermes-desktop` 仅在全部验收后替换。

## 任务 0：冻结现场并建立可验收清单

- [ ] 记录 `git rev-parse HEAD`、`git status --short`、`git merge-base main HEAD`、`F:\hermes-desktop\resources\install-stamp.json` 和 `Get-FileHash F:\hermes-desktop\resources\app.asar -Algorithm SHA256`；现有包基线为 2026-09-20 的 `a5e968d4...`，重测时以现场回执为准。记录 `Get-CimInstance Win32_Process` 对 `F:\hermes-desktop\Hermes.exe` 的 PID，不退出应用。
- [ ] 在 `localization-ledger.md` 建表 `surface | locale | state | source file | English visible | exclusion | behavior test | result`。枚举上述 Web 页面与 Desktop 的导航、设置、会话/右侧面板、能力/连接器、启动/更新；每个至少检查正常、空态和错误态。用户/服务商文本、模型名、命令、配置键及第三方插件是明确排除项。不得以 `en.ts` 与 `zh.ts` 行数推断缺译。
- [ ] 只读运行当前基线 `npm run check --workspace web`、`npm run typecheck --workspace apps/desktop`、`npm run test:ui --workspace apps/desktop`；记录测试总数和失败文件，特别是已观察到的 `voice-prefs`、`cron-detail`、`profile-config-capabilities`。后续同环境复跑用于比较，新增失败必须修复；既有失败不能记作绿灯。
- [ ] 确认 `F:\hermes-desktop` 不是 Git 仓库，`resources\app.asar`、`app.asar.unpacked`、`Hermes.exe` 均存在。提交审计清单，不碰现有程序。

## 任务 1：Web 的页面级漏译（按页面群执行红—绿—重构）

- [ ] **字典之外的红灯：** 扩展 `web/src/pages/McpPage.test.tsx` 中已存在的真实组件测试，分别 `localStorage.setItem('hermes-locale', 'zh')` / `'zh-hant'`，断言典型空态、按钮 accessible name、错误 toast 是对应中文，并且不包含 `Your MCP servers`；先运行 `npm test --workspace web -- src/pages/McpPage.test.tsx`，记录失败内容。
- [ ] **渠道与配置红灯：** 在 `web/src/pages/ChannelsPage.test.tsx` 针对已有 `localizeMessagingField` 的 QQ 群字段用例增补简/繁中断言；针对渠道错误态和 `web/src/pages/SkillsPage.tsx` 的学习弹窗，编写实际组件挂载测试（若无当前测试文件则新建同目录 `SkillsPage.test.tsx`）。示例行为断言为：

  ```tsx
  localStorage.setItem('hermes-locale', 'zh')
  render(<I18nProvider><McpPage /></I18nProvider>)
  expect(await screen.findByText(/已配置的 MCP 服务器/)).toBeTruthy()
  expect(screen.queryByText(/Your MCP servers/)).toBeNull()
  ```

- [ ] **最小绿灯：** 在本任务文件清单所列词典中加入经人工校对的简/繁中文，在页面消费现有 `t.*` 或 `pages*` 词条；`McpPage`、`ChannelsPage`、`SkillsPage` 已有一部分接线，不重复实现。新增动态描述保持现有函数参数、数组长度、占位符；服务商错误文本可附在已汉化的“操作失败：…”之后，不能修改原始诊断。
- [ ] **其余路由逐群：** 用审计清单对 `SystemPage`、Profiles/ProfileBuilder、Models/Sessions/Chat、Cron、Plugins/Pairing/Webhooks、Config、Files/Logs/Env/Analytics 逐一增加正常/空态/错误态行为测试、运行红灯、补当前源文件与对应字典、运行绿灯。每群独立提交，例如 `fix(web): localize profile and session controls`；每个路由必须在台账有“通过的测试路径”或“明确排除原因”，不能只写构建成功。
- [ ] 每群运行 `npm run typecheck --workspace web` 与相应 `npm test --workspace web -- src/pages/<实际文件>.test.tsx`；阶段末运行 `npm run check --workspace web`、`npm run build --workspace web`、`git diff --check`。预期新失败为 0，构建产物为 `hermes_cli/web_dist/index.html`。用实际 `zh`/`zh-hant` 页面走查台账中的交互。

## 任务 2：Desktop 页面级漏译（独立于 Web）

- [ ] 先用 `apps/desktop/src/i18n/catalog-completeness.test.ts`、同目录的 `context.test.tsx` 和代表性 `apps/desktop/src/app/settings/navigation-localization.test.tsx` 固定 `zh`/`zh-hant` 下键值类型、函数插值与真实可见导航；运行 `npm run test:ui --workspace apps/desktop -- src/i18n src/app/settings/navigation-localization.test.tsx`。字典能通过不意味着所有界面已汉化，新增页面测试必须针对用户眼见的英文。
- [ ] 按台账对 `apps/desktop/src/app/settings/` 中提供商、工具与密钥、插件、工作区、记忆、通知等表面，以及 `src/app/chat/` 中空态、错误卡、操作提示，逐群先写失败的组件渲染断言，再在最近的本地 i18n 字典增加译文、把硬编码改为 `useI18n().t`。示例期望：

  ```tsx
  render(<I18nProvider configClient={null} initialLocale="zh"><SettingsView onClose={vi.fn()} /></I18nProvider>)
  expect(await screen.findAllByText('消息密钥')).not.toHaveLength(0)
  expect(screen.queryByRole('button', { name: 'Message Keys' })).toBeNull()
  ```

- [ ] 对 `src/app/capabilities/`、`src/components/onboarding/`、`src/components/update-status.tsx` 与 `src/app/updates-overlay.tsx` 的首次启动、更新中/失败和登录/连接器流程执行同样红灯—绿灯；当上游首次添加英文键时，简/繁覆盖层都添加对应值，术语与 Web 一致。不为了通过“相等”断言删除 fork 专属的中文 QQ 文案。
- [ ] 每群运行相应 `npm run test:ui --workspace apps/desktop -- src/app/<对应目录>`、`npm run typecheck --workspace apps/desktop`、`npm run lint --workspace apps/desktop`，独立提交。阶段末运行 `npm run test:ui --workspace apps/desktop`、`npm run build --workspace apps/desktop`、`git diff --check`。若基线已有用例失败，至少额外重跑相关文件并对照任务 0；不宣称全量通过。

## 任务 3：Web 双端发布

- [ ] 固定提交 SHA 并再次从该提交运行 Web 全量检查与生产构建；核对 `hermes_cli/web_dist/index.html` 及 `assets/` 中文资源。记录源构建的入口 SHA256。
- [ ] 本机只更新 Dashboard 静态资源，不重启 QQBot/Gateway；在 `C:\Users\qwe57\AppData\Local\hermes\hermes-agent\hermes_cli\` 内先复制到 `web_dist.stage.<SHA>`，验证 SHA，再把旧 `web_dist` 改名 `web_dist.backup.<日期>`、stage 改为 `web_dist`。若第二步失败，立即改回；不得清理已有的旧备份。
- [ ] 对 130 经 SSH 在固定发布目录侧建 staging、核对 SHA、备份旧 `web_dist`、替换后只重启 `hermes-dashboard.service`；验证 `/login` 返回 200、`/health` 返回 ok、`hermes-gateway.service` 仍 active，文件日志出现 QQBot `Ready`。若任一服务不健康，恢复旧静态目录并重启 Dashboard；磁盘空间不足先停止发布。

## 任务 4：Desktop 侧装、冷启动与原目录切换

- [ ] 在所有 Desktop 相关门禁无新增失败、Git 已提交且工作树干净后，执行 `npm run pack --workspace apps/desktop`；其本质为 `npm run build && npm run builder -- --dir --publish never`，打包目标由 `apps/desktop/electron-builder.config.cjs` 指向 `apps/desktop/release/`。若缺签名、打包依赖或产物不存在，不碰 `F:\hermes-desktop`，报告真实阻断。
- [ ] 从 `apps/desktop/release/` 中确认新的 Windows unpacked 目录同时包含 `Hermes.exe`、`resources/app.asar`、`app.asar.unpacked`；复制到 `F:\hermes-desktop.stage.<SHA>`。用独立的 `--user-data-dir=F:\hermes-desktop-smoke-profile.<SHA>` 启动该目录的 `Hermes.exe`，核对启动/退出码、简繁中文切换及设置、聊天辅助控件、密钥、更新提示。旧 Desktop 保持运行且用户数据不被试运行写入。
- [ ] 冷启动通过后记录当前 `F:\hermes-desktop` 的 `app.asar` SHA256、进程 ID 与安装标记；关闭该目录的**所有** Hermes.exe 子进程并确认没有遗留 PID。用同盘目录改名把旧程序存为 `F:\hermes-desktop.backup.<日期>`，stage 改为 `F:\hermes-desktop`，绝不手工拆/覆盖旧 `app.asar`。启动新版后验证 `install-stamp` 指向交付 SHA、实际可见中/繁文案、Gateway/QQBot 未退化；如果新版失败，退出其进程，改回旧目录并验证旧版可以启动。用户原有 `C:\Users\qwe57\AppData\Roaming\Hermes` 保持原样。

## 任务 5：交付复核与报告

- [ ] 记录 Git 最终 SHA、Web/Desktop 测试通过/失败/跳过数、build 退出码、两端 Web hash、Desktop 原/新版 `app.asar` hash、启动进程路径与备份目录、130 服务状态；按台账逐页面给出已汉化/外部原文/未验证的真实状态。对照 `git diff --check main..HEAD` 和原始用户数据目录未改变的证据。
- [ ] 让审查者根据真实 diff 与测试回执复核；汉化 Code GO、Web 发布 GO、Desktop 发布 GO **分别裁定**。任何实际入口/`/message` 回复超时或模型供应商拒绝，只能标“对话未验证”，不能凭健康接口 HTTP 200 冒充可回复。

## 执行顺序与停线

审计 → Web 红/绿 → Desktop 红/绿 → 两端构建 → Web 发布 → Desktop 侧装 → 冷启动 → 原目录切换 → 报告。任何阶段出现与当前改动相关的测试失败、不可解释的文件变化、构建无法证明产物完整或旧目录回滚路径不可验证，停止后续发布并保留已提交源码与现行程序；不要用 `git reset --hard`、未授权的全盘清理或无法重现的人工替换绕过门禁。
