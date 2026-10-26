import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { join } from 'node:path'

import { app, BrowserWindow, safeStorage, session } from 'electron'
import { WebSocketServer } from 'ws'

import { buildGatewayWsUrlWithTicket, cookiesHaveLiveSession } from '../connection-config'
import { encryptDesktopSecret, writeSecretFileAtomic } from '../hardening'
import { createNativeAccessTokenCoordinator } from '../native-access-token'
import { parseTokenResponse, tokenNeedsRefresh } from '../native-oauth'
import { loadNativeTokenSet, type NativeTokenStoreIo, persistNativeTokenSet } from '../native-token-store'
import { createOauthLoginCompletion } from '../oauth-login-completion'
import { resolveOauthPartition } from '../oauth-partition'

// Two real Electron processes share only this disposable userData and its files.
const root = process.argv[2]
const phase = process.argv[3]
const statePath = join(root, 'state.json')
app.setPath('userData', join(root, 'user-data'))
app.on('window-all-closed', () => {})

let stage = 'boot'

const deadline = setTimeout(() => {
  console.error(`REMOTE_AUTH_TIMEOUT stage=${stage}`)
  app.exit(1)
}, 30_000)

async function run() {
  await app.whenReady()
  stage = 'ready'
  const previous = phase === 'restore' ? JSON.parse(readFileSync(statePath, 'utf8')) : null
  let logins = 0
  let refreshes = 0
  const tickets = new Set<string>()

  const server = createServer(async (request, response) => {
    response.setHeader('Content-Type', 'application/json')

    if (request.url === '/login') {
      logins += 1
      response.setHeader('Set-Cookie', 'hermes_session_at=fixture-cookie; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600')
      response.end('{}')

      return
    }

    if (request.url === '/auth/native/refresh') {
      if (request.headers.cookie) {
        response.writeHead(401).end('{}')

        return
      }

      let body = ''

      for await (const chunk of request) {
        body += chunk
      }

      assert.equal(JSON.parse(body).refresh_token, 'fixture-refresh')
      refreshes += 1
      response.end(
        JSON.stringify({
          access_token: 'fixture-rotated',
          refresh_token: 'fixture-refresh',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          provider: 'fixture',
          user_id: 'fixture-user'
        })
      )

      return
    }

    if (request.url === '/auth/ws-ticket' || request.url === '/auth/ws-ticket-native') {
      const authorized =
        request.url === '/auth/ws-ticket-native'
          ? !request.headers.cookie && request.headers.authorization === 'Bearer fixture-rotated'
          : request.headers.cookie?.includes('hermes_session_at=fixture-cookie')

      if (!authorized) {
        response.writeHead(401).end('{}')

        return
      }

      const ticket = randomUUID()
      tickets.add(ticket)
      response.end(JSON.stringify({ ticket }))

      return
    }

    response.writeHead(404).end('{}')
  })

  const sockets = new WebSocketServer({ noServer: true })
  server.on('upgrade', (request, socket, head) => {
    const ticket = new URL(request.url!, 'http://localhost').searchParams.get('ticket')!

    if (!tickets.delete(ticket)) {
      socket.end('HTTP/1.1 401 Unauthorized\r\n\r\n')

      return
    }

    sockets.handleUpgrade(request, socket, head, client => {
      client.on('message', bytes => {
        const rpc = JSON.parse(bytes.toString())
        client.send(JSON.stringify({ jsonrpc: '2.0', id: rpc.id, result: 'rpc-restored' }))
      })
    })
  })
  await new Promise<void>(resolve => server.listen(previous?.port ?? 0, '127.0.0.1', resolve))
  const port = (server.address() as AddressInfo).port
  const base = `http://127.0.0.1:${port}`

  const partition = resolveOauthPartition(base, {
    registry: {
      primary: 'local',
      connections: [{ id: 'restart-fixture', kind: 'remote', authMode: 'oauth', url: base }]
    }
  })

  const jar = session.fromPartition(partition)
  const other = session.fromPartition(`${partition}-other`)
  const nativePath = join(root, 'native.json')

  const io: NativeTokenStoreIo = {
    encrypt: text => encryptDesktopSecret(text, safeStorage),
    decrypt: secret => safeStorage.decryptString(Buffer.from(secret.value, 'base64')),
    readStoreText: () => readFileSync(nativePath, 'utf8'),
    writeStoreText: text => writeSecretFileAtomic(nativePath, text)
  }

  let window: BrowserWindow | null = null

  try {
    assert.equal(safeStorage.isEncryptionAvailable(), true)

    if (phase === 'login') {
      window = new BrowserWindow({
        show: false,
        webPreferences: { session: jar, sandbox: true, contextIsolation: true, nodeIntegration: false }
      })
      await window.loadURL(`${base}/login`)
      let completed = false

      const complete = createOauthLoginCompletion({
        hasSession: async () => cookiesHaveLiveSession(await jar.cookies.get({ url: base })),
        flushCookies: () => jar.cookies.flushStore(),
        onSuccess: () => {
          completed = true
        },
        onFailure: error => {
          throw error
        }
      })

      await Promise.all([complete(), complete()])
      assert.equal(completed, true)
      persistNativeTokenSet(
        base,
        {
          accessToken: 'fixture-expired',
          refreshToken: 'fixture-refresh',
          expiresAt: 1,
          provider: 'fixture',
          userId: 'fixture-user'
        },
        io
      )
      assert.doesNotMatch(readFileSync(nativePath, 'utf8'), /fixture-refresh|fixture-expired/)
    }

    stage = 'cookie-restore'
    assert.equal(cookiesHaveLiveSession(await jar.cookies.get({ url: base })), true)
    assert.equal(cookiesHaveLiveSession(await other.cookies.get({ url: base })), false)

    const cookieTicket = (await (await jar.fetch(`${base}/auth/ws-ticket`, { method: 'POST' })).json()) as {
      ticket: string
    }

    let nativeTicket: string | null = null

    if (phase === 'restore') {
      assert.notEqual(cookieTicket.ticket, previous.ticket)
      stage = 'native-refresh'

      const coordinator = createNativeAccessTokenCoordinator({
        normalizeBaseUrl: value => value,
        loadTokens: url => loadNativeTokenSet(url, io),
        clearTokens: url => persistNativeTokenSet(url, null, io),
        storeTokens: (url, tokens) => persistNativeTokenSet(url, tokens, io),
        isRefreshAuthRejection: () => false,
        tokenNeedsRefresh,
        refreshTokens: async (url, tokens) => {
          const response = await fetch(`${url}/auth/native/refresh`, {
            method: 'POST',
            body: JSON.stringify({ refresh_token: tokens.refreshToken }),
            headers: { 'Content-Type': 'application/json' }
          })

          assert.equal(response.status, 200)

          return parseTokenResponse(await response.json())
        }
      })

      const [first, second] = await Promise.all([coordinator.ensure(base), coordinator.ensure(base)])
      assert.equal(first, 'fixture-rotated')
      assert.equal(second, first)
      assert.equal(refreshes, 1)
      assert.equal(loadNativeTokenSet(base, io)?.accessToken, first)
      assert.equal(logins, 0)

      const response = await fetch(`${base}/auth/ws-ticket-native`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${first}` }
      })

      assert.equal(response.status, 200)
      nativeTicket = (await response.json()).ticket
      assert.ok(nativeTicket)
      assert.notEqual(nativeTicket, cookieTicket.ticket)
    } else {
      assert.equal(logins, 1)
    }

    stage = 'rpc'
    window ??= new BrowserWindow({
      show: false,
      webPreferences: { session: jar, sandbox: true, contextIsolation: true, nodeIntegration: false }
    })
    await window.loadURL(`${base}/ready`)

    for (const ticket of [cookieTicket.ticket, ...(nativeTicket ? [nativeTicket] : [])]) {
      const wsUrl = buildGatewayWsUrlWithTicket(base, ticket)

      const result = await window.webContents.executeJavaScript(
        `new Promise((resolve, reject) => { const ws = new WebSocket(${JSON.stringify(wsUrl)}); ws.onopen = () => ws.send(JSON.stringify({jsonrpc:'2.0',id:1,method:'ping'})); ws.onmessage = event => { resolve(JSON.parse(event.data).result); ws.close(); }; ws.onerror = () => reject(new Error('RPC connect failed')); })`
      )

      assert.equal(result, 'rpc-restored')
    }

    writeFileSync(statePath, JSON.stringify({ port, ticket: cookieTicket.ticket }))
    console.log(
      `REMOTE_AUTH_${phase.toUpperCase()}_OK cookie_persisted=true rpc=true login_requests=${logins} native_refreshes=${refreshes}`
    )
  } finally {
    window?.destroy()
    sockets.close()
    await new Promise<void>(resolve => server.close(() => resolve()))
  }
}

mkdirSync(root, { recursive: true })
run().then(
  () => {
    clearTimeout(deadline)
    app.exit(0)
  },
  () => {
    clearTimeout(deadline)
    console.error(`REMOTE_AUTH_RESTART_FAILED stage=${stage}`)
    app.exit(1)
  }
)
