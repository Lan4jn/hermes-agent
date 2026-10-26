import assert from 'node:assert/strict'

import { test } from 'vitest'

import { clearRemoteOauthSession } from './oauth-logout'

test('logout fences native identity before awaiting Cookie cleanup even when native deletion fails', async () => {
  const order: string[] = []
  const deletionError = new Error('native credential deletion failed')
  let release!: () => void

  const cookieGate = new Promise<void>(resolve => {
    release = resolve
  })

  const result = clearRemoteOauthSession({
    clearNativeTokens: () => {
      order.push('native-fenced')
      throw deletionError
    },
    clearCookies: async () => {
      order.push('cookies-start')
      await cookieGate
      order.push('cookies-cleared')
    }
  })

  const rejected = assert.rejects(result, error => error === deletionError)

  assert.deepEqual(order, ['native-fenced', 'cookies-start'])
  release()
  await rejected
  assert.deepEqual(order, ['native-fenced', 'cookies-start', 'cookies-cleared'])
})
