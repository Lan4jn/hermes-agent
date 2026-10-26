# Desktop 远程登录持久恢复设计

## 已确认目标
用户选择一次登录后，退出并启动 Desktop 或 Windows 重启再启动 Desktop，自动恢复原远程连接。保留 Gateway 鉴权，不设置 Windows 开机启动，不复制跨 Gateway Cookie，不保存密码。既有原生 OAuth 与 Cookie 登录均需支持。

## 现场与边界
隔离工作树基线 c83be20520。实际 kylin 连接为 http://192.168.31.130:9119，远程服务器广告 basic 密码 Provider 与 cookie/native_pkce flow。Desktop 对密码登录选择 embedded Cookie 流程，这是既有 oauth authMode 的含义。原生 Token 文件零记录不能用来证明 Cookie 登录失效。真实 Cookie 分区被运行中的 Desktop 锁定，未停用户应用，不读取 Cookie 值。

## 架构
复用连接注册表与启动恢复、稳定 persist 分区、原生 Token store、single-flight refresh coordinator、每次拨号重新签发的 WS ticket。Electron 是秘密持久化权威；renderer 仅维护连接显示与既有启动选择。Cookie 分区仍按现有连接规则隔离，不迁移旧共享分区凭据。

## 持久完成语义
Cookie 登录检测到会话后，等待 cookies.flushStore 成功才关闭登录窗口并返回成功；重叠导航与轮询合并为一次完成流程。写盘失败用固定、无秘密错误拒绝登录完成，不谎报可重启恢复。原生 Token 保存失败须抛给登录/刷新调用方；采用现有原子秘密文件写入器，不让截断文件成为持久记录。缓存只在成功写盘后更新。

## 启动选择与凭据策略
复用现有 launchMode 与显式 defaultProfileRoute：若用户设置显式默认连接，则启动它；否则 last-used 模式恢复 lastUsed，primary 模式启动 primary。当前真实配置 primary=local、lastUsed=local、launchMode=primary，因此要自动进入 kylin 必须在设置中选择最后使用的连接并成功选择 kylin，或把 kylin 设为显式启动默认。本修复不偷偷覆盖已有启动偏好。

原生秘密写入仍遵循既有 secretStoragePolicy。安全存储开启时通过 safeStorage 保护；用户显式关闭时既有策略允许 owner-only 文件明文，不能声称所有策略下都加密。本次不修改全局开关；验收 fixture 的原生 Token 使用严格 Windows safeStorage，仅证明开启安全存储时的真实恢复。密码不写入 Desktop 持久配置，日志不打印任何真实秘密。

## 恢复与安全
保留现有规范化 URL 键、Cookie 分区与 refresh coordinator 的身份栅栏。网络超时/5xx 不删凭据；只有明确 refresh 鉴权撤销才清理；OAuth WS ticket 不复用。退出登录先使并发原生流程失效，即使原生持久删除失败也通过 finally 执行 Cookie 清理；删除失败明确报告残留凭据，不全局吞错。删除不存在的原生记录不写磁盘，不阻断 Cookie-only 登录。任何临时 fixture 使用独立 userData、虚构凭据、loopback server，不触碰真实 Cookie/密码。

## 验收
单元测试先红后绿：native write failure 不成功；Cookie flush 完成前不成功、并发合并、失败不成功。回归原生刷新、身份变化、一次性票据、分区隔离、连接选择恢复。真实 Electron 两个独立进程共用临时 userData，首次完成 Cookie 登录并退出，第二次不登录即可签发全新 WS ticket 并建立 RPC 连接；确认实际 Cookie persist 分区与写盘。原生持久 store→fresh coordinator→cookieless refresh→parseTokenResponse→Bearer ticket→RPC 同样由两个真实 Electron 进程验证；原生测试路由拒绝 Cookie 认证，不允许 Cookie 掩盖失败。Windows 整机重启与真实 130 登录需人机确认，不伪造完成证据。

## 不包含
新认证系统、永久无限寿命凭据、关闭鉴权、明文密码、自动迁移 Cookie、Windows 自动启动、未经用户同意终止当前 Desktop 或重启 Windows。
