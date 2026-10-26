import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { atom } from 'nanostores'
import { MemoryRouter, useNavigate } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { stubResizeObserver } from '@/test/jsdom'

import { envVar } from './test-utils'

const getEnvVars = vi.fn()
const testConnectionId = atom<null | string>('test-conn')

stubResizeObserver()

vi.mock('@/hermes', () => ({
  deleteEnvVar: vi.fn(),
  getEnvVars: (profile?: null | string) => getEnvVars(profile),
  getProfiles: vi.fn().mockResolvedValue({ profiles: [] }),
  revealEnvVar: vi.fn(),
  setApiRequestProfile: () => undefined,
  setEnvVar: vi.fn()
}))

vi.mock('@/store/connections', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    $activeConnectionId: testConnectionId
  }
})

vi.mock('@/store/session', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    $gatewayState: {
      get: () => 'open',
      listen: () => () => {},
      subscribe: (fn: any) => {
        fn('open')

        return () => {}
      },
      value: 'open'
    }
  }
})

const mockGatewayRpc = vi.fn()

vi.mock('@/store/gateway', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    requestGatewayForAgent: (conn: any, prof: any, method: string, params: any) => {
      if (mockGatewayRpc.getMockImplementation()) {
        return mockGatewayRpc(conn, prof, method, params)
      }

      if (method === 'message_keys.list') {return Promise.resolve({ items: [] })}

      if (method === 'message_keys.get_policy') {return Promise.resolve({ require_chat_key: false })}

      return Promise.resolve({})
    }
  }
})

// Load once at module scope so no test's 15s budget pays the heavy transform
// + import (the first-test timeout flake under CI load).
const { KeysSettings } = await import('./keys-settings')
const { $settingsScopeOverride } = await import('@/store/settings-scope')

beforeEach(() => {
  testConnectionId.set('test-conn')
  mockGatewayRpc.mockReset()
  getEnvVars.mockResolvedValue({})
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn()
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

async function renderKeysSettings(view: 'settings' | 'tools', route = '/settings') {
  await act(async () => {
    render(
      <MemoryRouter initialEntries={[route]}>
        <KeysSettings view={view} />
      </MemoryRouter>
    )
  })
}

function DeepLinkButton({ target }: { target: string }) {
  const navigate = useNavigate()

  return (
    <button onClick={() => navigate(`/settings?tab=keys&key=${target}`)} type="button">
      Open key
    </button>
  )
}

describe('KeysSettings', () => {
  it('fetches env vars for the displayed profile (the concrete key, never null) when unscoped', async () => {
    // #90549 class: getEnvVars(null) targets the primary profile's env store,
    // so a non-default profile's Keys page would read (and edit) the wrong
    // profile. #118432: `undefined` is equally wrong — profileScoped() then
    // drops `?profile=` entirely and the backend falls back to the home it was
    // LAUNCHED under, which need not be the profile this page displays. Send
    // the concrete key the page names.
    await renderKeysSettings('tools')

    await waitFor(() => expect(getEnvVars).toHaveBeenCalledWith('default'))
  })

  it('lists tools and excludes settings / channel-managed credentials', async () => {
    getEnvVars.mockResolvedValue({
      BRAVE_SEARCH_API_KEY: envVar('tool', { description: 'Search the web with Brave.' }),
      FIRECRAWL_API_KEY: envVar('tool', { description: 'Crawl and extract websites.' }),
      GATEWAY_PROXY: envVar('setting', { description: 'Gateway reverse proxy.' }),
      TELEGRAM_BOT_TOKEN: envVar('messaging', {
        channel_managed: true,
        description: 'Telegram bot token.'
      })
    })

    await renderKeysSettings('tools')

    expect(screen.getByText('BRAVE SEARCH')).toBeTruthy()
    expect(screen.getByText('FIRECRAWL')).toBeTruthy()
    expect(screen.queryByText('GATEWAY PROXY')).toBeNull()
    expect(screen.queryByText('TELEGRAM BOT')).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('lists settings rows and excludes tools / channel-managed credentials', async () => {
    getEnvVars.mockResolvedValue({
      API_SERVER_TOKEN: envVar('setting', { description: 'Protect the local API server.' }),
      GATEWAY_PROXY: envVar('messaging', { description: 'Gateway reverse proxy address.' }),
      TELEGRAM_BOT_TOKEN: envVar('messaging', {
        channel_managed: true,
        description: 'Telegram bot token.'
      }),
      BRAVE_SEARCH_API_KEY: envVar('tool', { description: 'Search the web with Brave.' })
    })

    await renderKeysSettings('settings')

    expect(screen.getByText('API SERVER')).toBeTruthy()
    expect(screen.getByText('GATEWAY PROXY')).toBeTruthy()
    expect(screen.queryByText('TELEGRAM BOT')).toBeNull()
    expect(screen.queryByText('BRAVE SEARCH')).toBeNull()
  })

  it('expands and highlights a deep-linked credential card', async () => {
    getEnvVars.mockResolvedValue({
      BRAVE_SEARCH_API_KEY: envVar('tool', { description: 'Search the web with Brave.' }),
      FIRECRAWL_API_KEY: envVar('tool', { description: 'Crawl and extract websites.' })
    })

    render(
      <MemoryRouter initialEntries={['/settings?tab=keys']}>
        <KeysSettings view="tools" />
        <DeepLinkButton target="FIRECRAWL_API_KEY" />
      </MemoryRouter>
    )

    expect(await screen.findByText('BRAVE SEARCH')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Open key' }))

    await waitFor(() => {
      const target = globalThis.document.getElementById('credential-key-FIRECRAWL_API_KEY')
      expect(target?.classList).toContain('setting-field-highlight')
    })
    expect(screen.getByText('Crawl and extract websites.')).toBeTruthy()
  })

  it('drops an unsaved credential edit when the settings target switches profile', async () => {
    // Regression: `vars` is re-fetched when the shared "Applies to" target
    // changes, but the in-flight edit map was not reset with it. A value typed
    // while targeting profile-b survived the switch to profile-c, where the
    // still-live Save would persist it into the WRONG profile.
    $settingsScopeOverride.set('profile-b')
    getEnvVars.mockResolvedValue({
      WIDGET_API_KEY: envVar('tool', { description: 'Widget key.', is_set: true, redacted_value: '••••••' })
    })

    try {
      const { container } = render(
        <MemoryRouter initialEntries={['/settings']}>
          <KeysSettings view="tools" />
        </MemoryRouter>
      )

      expect(await screen.findByText('WIDGET')).toBeTruthy()
      await waitFor(() => expect(getEnvVars).toHaveBeenCalledWith('profile-b'))

      // Open the field and type a value without saving it.
      fireEvent.focus(container.querySelector('input[readonly]') as HTMLInputElement)
      fireEvent.change(container.querySelector('input[type="password"]') as HTMLInputElement, {
        target: { value: 'typed-secret' }
      })

      expect(screen.getByDisplayValue('typed-secret')).toBeTruthy()

      // Re-target Settings at another profile. This is where the leak
      // manifested: the draft stayed live, so the (still-rendered) Save would
      // dispatch it through setEnvVar against the NEW target.
      await act(async () => {
        $settingsScopeOverride.set('profile-c')
      })
      await waitFor(() => expect(getEnvVars).toHaveBeenCalledWith('profile-c'))

      // The draft belonged to the previous target: it is gone, and so is the
      // Save control that would have dispatched it — no path is left that can
      // write the stale value into the profile now being targeted.
      expect(screen.queryByDisplayValue('typed-secret')).toBeNull()
      expect(screen.queryByRole('button', { name: 'Save' })).toBeNull()
    } finally {
      cleanup()
      $settingsScopeOverride.set(null)
    }
  })

  it('switches view across tools -> message -> settings -> message -> tools on the same mounted instance without hook errors', async () => {
    getEnvVars.mockResolvedValue({
      BRAVE_SEARCH_API_KEY: envVar('tool', { description: 'Search tool' }),
      API_SERVER_TOKEN: envVar('setting', { description: 'API server token' })
    })

    const { rerender } = render(
      <MemoryRouter initialEntries={['/settings']}>
        <KeysSettings view="tools" />
      </MemoryRouter>
    )

    expect(await screen.findByText('BRAVE SEARCH')).toBeTruthy()

    // Switch to message
    await act(async () => {
      rerender(
        <MemoryRouter initialEntries={['/settings']}>
          <KeysSettings view="message" />
        </MemoryRouter>
      )
    })
    expect(await screen.findByText('Enforcement Policy')).toBeTruthy()

    // Switch to settings
    await act(async () => {
      rerender(
        <MemoryRouter initialEntries={['/settings']}>
          <KeysSettings view="settings" />
        </MemoryRouter>
      )
    })
    expect(await screen.findByText('API SERVER')).toBeTruthy()

    // Switch back to message
    await act(async () => {
      rerender(
        <MemoryRouter initialEntries={['/settings']}>
          <KeysSettings view="message" />
        </MemoryRouter>
      )
    })
    expect(await screen.findByText('Enforcement Policy')).toBeTruthy()

    // Switch back to tools
    await act(async () => {
      rerender(
        <MemoryRouter initialEntries={['/settings']}>
          <KeysSettings view="tools" />
        </MemoryRouter>
      )
    })
    expect(await screen.findByText('BRAVE SEARCH')).toBeTruthy()
  })

  it('does not request env credentials when mounting or rendering message view', async () => {
    getEnvVars.mockClear()
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <KeysSettings view="message" />
      </MemoryRouter>
    )

    expect(await screen.findByText('Enforcement Policy')).toBeTruthy()
    expect(getEnvVars).not.toHaveBeenCalled()
  })

  it('clears sensitive one-time key and resets message state when switching active connection A -> B', async () => {
    testConnectionId.set('conn-a')
    mockGatewayRpc.mockImplementation((conn, _prof, method) => {
      if (method === 'message_keys.list') {
        if (conn === 'conn-a') {
          return Promise.resolve({ items: [{ id: 'key-a', name: 'key-for-conn-a', created_at: '2026-09-26T00:00:00Z' }] })
        }

        return Promise.resolve({ items: [{ id: 'key-b', name: 'key-for-conn-b', created_at: '2026-09-26T00:00:00Z' }] })
      }

      if (method === 'message_keys.get_policy') {return Promise.resolve({ require_chat_key: false })}

      if (method === 'message_keys.create') {
        return Promise.resolve({ id: 'key-new', name: 'new-key', key: 'hmmsg_plaintext_conn_a_secret', created_at: '2026-09-26T00:00:00Z' })
      }

      return Promise.resolve({})
    })

    render(
      <MemoryRouter initialEntries={['/settings']}>
        <KeysSettings view="message" />
      </MemoryRouter>
    )

    expect(await screen.findByText('key-for-conn-a')).toBeTruthy()

    // Create a key in conn-a to produce plaintext secret
    fireEvent.click(await screen.findByText('Create Key'))
    const input = await screen.findByPlaceholderText('e.g. openclaw-gateway, router-node')
    fireEvent.change(input, { target: { value: 'new-key' } })
    const createBtn = screen.getAllByRole('button', { name: /create/i }).pop()!
    fireEvent.click(createBtn)

    // Sensitive one-time key banner is shown for conn-a
    expect(await screen.findByText('Copy Your New Message Key')).toBeTruthy()
    expect(screen.getByDisplayValue('hmmsg_plaintext_conn_a_secret')).toBeDefined()

    // Now switch active connection from conn-a to conn-b
    await act(async () => {
      testConnectionId.set('conn-b')
    })

    // Assert: Conn-B items are rendered, and Conn-A's one-time key is immediately wiped
    expect(await screen.findByText('key-for-conn-b')).toBeTruthy()
    expect(screen.queryByText('Copy Your New Message Key')).toBeNull()
    expect(screen.queryByDisplayValue('hmmsg_plaintext_conn_a_secret')).toBeNull()
    expect(screen.queryByText('key-for-conn-a')).toBeNull()

    // Switch back to conn-a: one-time key must NEVER restore
    await act(async () => {
      testConnectionId.set('conn-a')
    })
    expect(await screen.findByText('key-for-conn-a')).toBeTruthy()
    expect(screen.queryByText('Copy Your New Message Key')).toBeNull()
    expect(screen.queryByDisplayValue('hmmsg_plaintext_conn_a_secret')).toBeNull()
  })

  it('discards an in-flight list response from connection A after switching to B', async () => {
    testConnectionId.set('conn-a')
    let resolveStaleListA!: (value: any) => void

    const pendingListAPromise = new Promise(res => {
      resolveStaleListA = res
    })

    mockGatewayRpc.mockImplementation((conn, _prof, method) => {
      if (method === 'message_keys.list') {
        if (conn === 'conn-a') {
          return pendingListAPromise
        }

        return Promise.resolve({ items: [{ id: 'key-b', name: 'key-on-conn-b', created_at: '2026-09-26T00:00:00Z' }] })
      }

      if (method === 'message_keys.get_policy') {return Promise.resolve({ require_chat_key: false })}

      return Promise.resolve({})
    })

    render(
      <MemoryRouter initialEntries={['/settings']}>
        <KeysSettings view="message" />
      </MemoryRouter>
    )

    // Switch to conn-b before conn-a resolves
    await act(async () => {
      testConnectionId.set('conn-b')
    })

    expect(await screen.findByText('key-on-conn-b')).toBeTruthy()

    // Now late resolve conn-a's pending list
    await act(async () => {
      resolveStaleListA({ items: [{ id: 'key-a-stale', name: 'STALE_KEY_A', created_at: '2026-09-26T00:00:00Z' }] })
    })

    // Assert: STALE_KEY_A must not be rendered or pollute conn-b
    expect(screen.queryByText('STALE_KEY_A')).toBeNull()
    expect(screen.getByText('key-on-conn-b')).toBeTruthy()
  })

  it('closes the revoke dialog and ignores its late response after switching connections', async () => {
    testConnectionId.set('conn-a')
    let resolveRevoke!: (value: { ok: boolean; removed: boolean }) => void

    const pendingRevoke = new Promise<{ ok: boolean; removed: boolean }>(resolve => {
      resolveRevoke = resolve
    })

    mockGatewayRpc.mockImplementation((conn, _prof, method) => {
      if (method === 'message_keys.list') {
        return Promise.resolve({
          items: [{ id: `key-${conn}`, name: `key-on-${conn}`, created_at: '2026-09-26T00:00:00Z' }]
        })
      }

      if (method === 'message_keys.get_policy') {return Promise.resolve({ require_chat_key: false })}

      if (method === 'message_keys.revoke') {return pendingRevoke}

      return Promise.resolve({})
    })

    render(
      <MemoryRouter initialEntries={['/settings']}>
        <KeysSettings view="message" />
      </MemoryRouter>
    )
    expect(await screen.findByText('key-on-conn-a')).toBeTruthy()
    const revokeButton = screen.getAllByRole('button').find(button => button.className.includes('text-destructive'))
    expect(revokeButton).toBeDefined()
    fireEvent.click(revokeButton!)
    expect(await screen.findByText('Revoke Message Key')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }))
    await waitFor(() => expect(mockGatewayRpc).toHaveBeenCalledWith('conn-a', 'default', 'message_keys.revoke', { id: 'key-conn-a' }))

    await act(async () => {
      testConnectionId.set('conn-b')
    })
    expect(await screen.findByText('key-on-conn-b')).toBeTruthy()
    expect(screen.queryByText('Revoke Message Key')).toBeNull()

    await act(async () => {
      resolveRevoke({ ok: true, removed: true })
    })
    expect(screen.getByText('key-on-conn-b')).toBeTruthy()
    expect(screen.queryByText('key-on-conn-a')).toBeNull()
    expect(mockGatewayRpc).not.toHaveBeenCalledWith('conn-b', 'default', 'message_keys.revoke', expect.anything())
  })
})
