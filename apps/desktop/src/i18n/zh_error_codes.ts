import type { Translations } from './types'

type ThreadCopy = Translations['assistant']['thread']

// The error card's per-code title and body (lib/error-surface-copy.ts), keyed by error_surface.code.
export const zhErrorCodes: Partial<ThreadCopy['errorCodes']> = {
  cron_session_read_only: {
    title: '此聊天属于一个定时任务',
    body: '它只运行该任务，因此你的消息未被执行。请新建聊天后再发送。'
  },
  session_read_only: {
    title: '此聊天为只读',
    body: '它是 Hermes 只能显示、无法继续的已保存历史记录，因此你的消息未被执行。请新建聊天后再发送。'
  },
  workspace_unavailable: {
    title: '此聊天的文件夹已不存在',
    body: '此聊天使用的文件夹已被移动或删除，因此你的消息未被执行。请重新创建该文件夹，或使用“移动到项目”为聊天指定其他文件夹，然后重试。'
  },
  launch_credentials_unavailable: {
    title: '此聊天的 API 密钥已更改',
    body: '此聊天开始时使用的 API 密钥后来已被更改或删除，因此你的消息未发送。打开的聊天不会自行切换到其他密钥。请使用“开始新会话”以使用当前密钥。'
  },
  billing: {
    title: '额度不足',
    body: provider => `您的 ${provider} 账户额度已用尽。请充值或切换服务商，然后重新发送。`
  },
  stream_drop: {
    title: '流式连接错误',
    body: '回复完成前连接已断开。请重试以重新发送。'
  },
  disk_full: {
    title: '磁盘已满',
    body: '磁盘空间已满，Hermes 无法保存此对话。请清理一些空间后重试。'
  },
  auth: {
    title: provider => `${provider} 拒绝了您的登录`,
    body: provider => `保存的 ${provider} 凭据未被接受。请在“设置”中修正或切换服务商，然后重新发送消息。`
  },
  auth_permanent: {
    title: provider => `${provider} 拒绝了您的登录`,
    body: provider => `保存的 ${provider} 凭据无效或已被撤销。请更新凭据或切换服务商，然后重新发送消息。`
  },
  upstream_blocked: {
    title: '防火墙拦截了请求',
    body: provider =>
      `${provider} 前端的防火墙或 CDN 在请求到达模型之前拦截了该请求——您的密钥可能没有问题。请在“设置”中通过该服务商的 extra_headers 设置 User-Agent 请求头，或切换服务商，然后重新发送消息。`
  },
  context_overflow: {
    title: '对话内容过长',
    body: '对话内容已超出模型限制。请压缩对话或开启新会话，然后重新发送。'
  },
  payload_too_large: {
    title: '此消息过大',
    body: '请求内容超出该模型的处理限制。请压缩对话或开启新聊天，然后重新发送。'
  },
  model_not_found: {
    title: '该模型不可用',
    body: provider => `${provider} 未在您的账户中提供此模型。请选择其他模型，然后重新发送消息。`
  },
  truncated: {
    title: '回复被截断',
    body: '模型在完成前停止生成。请重试以获取完整回复。'
  },
  loop_error: {
    title: 'Hermes 陷入了循环',
    body: '回复一直在重复相同的步骤，因此 Hermes 终止了该操作。请重试，如果再次发生请开启新聊天。'
  },
  SESSION_NOT_OWNED: {
    title: '此聊天已在其他地方打开',
    body: '此聊天当前已在另一个 Hermes 窗口或终端中打开。请在对应位置将其关闭后重新发送消息，或在此处开启新聊天。'
  },
  free_tier_disabled: {
    title: '免登录使用 Hermes 功能当前已关闭',
    body: '登录 Nous 账户即可继续聊天，完全免费。'
  },
  free_tier_rate_limited: {
    title: '您未登录状态下的对话额度已用尽',
    body: '额度很快会刷新。登录 Nous 账号可获得更多额度，完全免费。'
  },
  free_tier_at_capacity: {
    title: '当前未登录对话服务非常繁忙',
    body: '登录即可免排队（完全免费），或者稍后重试。'
  },
  free_tier_model_not_free: {
    title: '未登录状态下无法使用该模型',
    body: 'Hermes 目前使用的是免费模型。登录 Nous 账号可使用更多模型，完全免费。'
  },
  free_tier_route: {
    title: 'Hermes 无法通过此路由连接到免费模型',
    body: '登录 Nous 账号（完全免费），或检查 NOUS_INFERENCE_BASE_URL 设置。'
  },
  free_tier_outage: {
    title: '免费模型暂时无法响应',
    body: '请过一分钟后重试发送。'
  },
  free_tier_refused: {
    title: '未登录时 Hermes 无法发送该内容',
    body: '登录 Nous 账号完全免费。'
  }
}
