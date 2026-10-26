import assert from 'node:assert/strict'

import { test } from 'vitest'

import { createOauthLoginCompletion } from './oauth-login-completion'

test('login completion waits for one durable cookie flush across concurrent checks', async () => {
  let release!: () => void

  const flushed = new Promise<void>(resolve => {
    release = resolve
  })

  let flushes = 0
  let successes = 0

  const check = createOauthLoginCompletion({
    hasSession: async () => true,
    flushCookies: async () => {
      flushes += 1
      await flushed
    },
    onSuccess: () => {
      successes += 1
    },
    onFailure: () => assert.fail('durable flush must complete login')
  })

  const first = check()
  const second = check()

  await Promise.resolve()
  assert.equal(flushes, 1)
  assert.equal(successes, 0)
  release()
  await Promise.all([first, second])
  await check()
  assert.equal(successes, 1)
  assert.equal(flushes, 1)
})

test('unsigned checks remain retryable but a failed persistence never reports login success or leaks its error', async () => {
  let signedIn = false
  let successes = 0
  const errors: Error[] = []

  const check = createOauthLoginCompletion({
    hasSession: async () => signedIn,
    flushCookies: async () => {
      throw new Error('cookie-secret')
    },
    onSuccess: () => {
      successes += 1
    },
    onFailure: error => errors.push(error)
  })

  await check()
  assert.equal(errors.length, 0)
  signedIn = true
  await Promise.all([check(), check()])
  await check()
  assert.equal(successes, 0)
  assert.equal(errors.length, 1)
  assert.match(errors[0].message, /could not be saved/)
  assert.doesNotMatch(errors[0].message, /cookie-secret/)
})
