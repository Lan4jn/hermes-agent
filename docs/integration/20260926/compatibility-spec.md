# Hermes Fork 个性化特性兼容性与行为保全规范 (Compatibility Spec)

## 一、 `/message` 权限契约与接口规范

### 1. 认证分级与默认策略
- **默认开放聊天**：`require_chat_key` 默认值为 `false`，存储于 SQLite 数据表 `message_api_keys_policy` 中，保证开箱即用且持久化保存；
- **权限严格隔离**：
  - **通话密钥 (`chat_key`)**：仅用于当 `require_chat_key = true` 时校验用户消息发送权限。**绝对不可**用于授权系统命令执行 (`command`)，**绝对不可**用于签发执行令牌 (`exec_token`)；
  - **管理密钥 (`api_key` / `Bearer`)**：拥有全局最高权限，可直接授权命令执行、签发临时 `exec_token` 并操作密钥策略；
  - **执行令牌 (`exec_token`)**：仅由管理密钥签发的短期 URL-Safe 令牌（默认 TTL 3600 秒），仅可用于在限定时间内执行命令，不可作为聊天凭证。
- **会话与身份隔离**：
  - 显式传递 `session_id` 或 `sender_id` 时，按照 `message_api:<id>` 进行会话状态与记忆追踪；
  - 未传递任何身份标识的匿名请求，服务端自动为其分配 `anon-{secrets.token_urlsafe(24)}` 独立临时会话，各请求间严密隔离，杜绝跨会话状态泄漏。
- **稳定性与错误脱敏**：
  - 网关处于 draining（优雅停机）阶段时，返回 503 与 Retry-After 标头；
  - 任何内部异常对外部调用者统一脱敏返回 `{"error": "message processing failed"}`，详细栈追溯记入安全日志。

---

## 二、 消息专用密钥管理规范 (Message-Only Keys)

### 1. 生命周期与交互语义
- **创建单次回显**：新建密钥时生成以 `hmmsg_` 为前缀的高强度随机字符串，明文仅在创建响应中返回一次，后端仅存储加盐 SHA-256 哈希值或安全索引；
- **撤销即时生效**：支持通过 Web 控制台、Desktop 客户端或 JSON-RPC 接口 (`message_keys.revoke`) 实时注销，底层查询即时失效；
- **双端无缝对齐**：Web UI（`MessageKeysSection.tsx`）与 Desktop 客户端（`message-keys-setting.tsx`）均保持统一的中英多语言文案，提供复制成功轻提示与二次确认对话框。

---

## 三、 Desktop 客户端生命周期与安全隔离规范 (S1 ~ S5)

### 1. React Rules of Hooks 顶层无条件执行保证 (S1 & S2)
- **纯路由派发架构**：`KeysSettings` 作为根容器组件，**绝对不可**在调用 Hook 之前出现条件分支或提前 `return`；
- **子视图 Hook 物理隔离**：环境变量相关的重度 Hooks（如 `useSecretsEnv`、`useConnectionCapabilities` 等）严格封装在独立的叶子子组件（如 `EnvCredentialsSettings`）内部，只在进入对应工具或环境变量子视图时按需挂载；
- **按需加载与空载保证**：当用户在 `tools → message → settings → message → tools` 等复杂路径快速来回切换子视图时，Hook 调度链长度绝对保持恒定，在 `message` 视图下绝不触发环境变量 RPC 查询。

### 2. 多 Profile / 连接切换敏感数据即时擦除 (S3 & S4)
- **DOM / State 彻底卸载**：通过外层挂载动态 Key：`key={`${connectionId}:${scopeProfile ?? 'default'}`}`，在用户切换连接或 Profile 时强迫 React 销毁旧组件实例并重置全部局部状态；
- **一次性明文密钥即时擦除 (S3)**：一旦发生 Profile 或连接变更，`oneTimeKey`、`pendingRevoke` 以及表单草稿等敏感状态必须在 `useEffect` 第一时间置为 `null`，且在用户再次切换回原 Profile 时绝对不可复现或残留；
- **在途异步请求取消与版本防污染 (S4)**：内部持有最新的 `identityRef` 标记。慢速网络或并发延迟返回的列表查询/创建回调在落地前必须比对当前 `identityRef`，若与发信时的连接/Profile 不一致，必须坚决废弃，严禁旧请求结果覆盖或污染新选中的 Profile。

### 3. 多语言导航与本地化规范 (S5)
- **统一导航 Token**：消除设置侧边栏中硬编码的 `'Message Keys'` 字符串，统一使用 `t.settings.nav.keysMessage` 驱动；
- **全语种字典覆盖**：在 `en`, `zh`, `zh-hant`, `ja`, `ar`, `ru` 7 个语言字典中保持 100% 同步翻译并由自动化契约测试覆盖。

---

## 四、 QQBot 消息网关增强规范

### 1. 多类型附件处理链路
- **下载与缓存兼容性**：适配器方法 `_download_and_cache_attachment` 自动兼容 2 参数与 3 参数（含 `channel_id`）历史签名；
- **文本型附件注入**：扩展支持 `.yml`, `.yaml`, `.sql`, `.properties`, `.conf`, `.ini`, `.tsv`, `.jsonl`, `.sh`, `.py`, `.js` 等文本文档类型。符合规则的文件自动提取安全截断摘要（最长 4000 字符），组装并注入上下文；
- **图片多模态路由**：图片类型附件直接组装进入模型的视觉流（Vision pipeline）；
- **执行审批降级**：平台支持 Interactive Card 审批按钮；若对端客户端不支持交互卡片，自动平滑回退为纯文本指令提示。

### 2. Fake-IP 与内网安全白名单 (SSRF 防御)
- 在 `tools/url_safety.py` 中，针对 QQ 开放平台核心域名（`api.sgroup.qq.com`、`bots.qq.com`）显式放行内网 IP 解析（适配特定网络下代理或 VPN 将域名解析为 Fake-IP 198.18.0.0/15 的场景）；
- 其余非白名单请求严格执行私有 IP / 回环地址阻断，确保 SSRF 防御机制完整生效。

---

## 五、 Google Gemini CLI / Code Assist OAuth 代理规范

### 1. 协议实现与端点反向代理
- 包含 `agent/google_oauth.py`、`agent/gemini_endpoints.py`、`agent/google_code_assist.py`、`agent/gemini_cloudcode_adapter.py`；
- 支持用户使用 Google 账号完成 PKCE 授权流，自动在后台维护 Access Token 的定时刷新；
- 在请求转发层支持自定义端点与反向代理，解决特定地区网络阻断问题；
- 命令行支持 `hermes auth login google-gemini-cli`、`hermes auth logout` 以及 `/gquota` 配额实时查询。

---

## 六、 工具门禁收敛与 Footprint Ladder 规范

### 1. 收敛规则
- `send_hermes_message` **严禁** 作为全局无差别工具放在 `_HERMES_CORE_TOOLS` 中；
- 将 `send_hermes_message` 精准配置在：
  - `TOOLSETS["hermes-api-server"]`：供 API 节点与服务网关使用；
  - `TOOLSETS["peer_messaging"]`：供用户配置跨节点对等通信时使用；
- 配合 `check_fn=is_hermes_message_server_configured`，确保即使 toolset 被激活，当且仅当配置了 peers 或开启了 api_server 时才向大模型注入该工具，彻底收敛核心工具占用。

---

## 七、 锁文件治理与无冲突原则 (S6)
- 依赖锁文件与配置必须使用官方包管理器（`uv lock`、`npm`）原生生成，严禁任何形式的手写冲突标记；
- 提交前必须通过 `uv lock --check` 以及 `git diff --check` 双重校验。
