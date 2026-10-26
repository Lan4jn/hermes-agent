import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { testScopeProfile, testConnectionId, testGatewayState } = vi.hoisted(() => {
  const createMockAtom = (initialValue: any) => {
    let val = initialValue
    let listeners: any[] = []

    return {
      get: () => val,
      set: (newVal: any) => {
        val = newVal
        listeners.forEach(fn => fn(val))
      },
      listen: (fn: any) => {
        listeners.push(fn)

        return () => {
          listeners = listeners.filter(l => l !== fn)
        }
      },
      subscribe: (fn: any) => {
        listeners.push(fn)
        fn(val)

        return () => {
          listeners = listeners.filter(l => l !== fn)
        }
      }
    }
  }

  return {
    testScopeProfile: createMockAtom('default'),
    testConnectionId: createMockAtom('test-conn'),
    testGatewayState: createMockAtom('open')
  }
})

const requestGatewayMock = vi.fn()

vi.mock('@/store/session', () => ({
  $gatewayState: testGatewayState
}))

vi.mock('@/store/connections', () => ({
  $activeConnectionId: testConnectionId
}))

vi.mock('@/store/settings-scope', () => ({
  $settingsScopeProfile: testScopeProfile
}))

vi.mock('@/store/gateway', () => ({
  requestGatewayForAgent: (...args: any[]) => requestGatewayMock(...args)
}))

vi.mock('@/store/notifications', () => ({
  notify: vi.fn(),
  notifyError: vi.fn()
}))

vi.mock('@/lib/haptics', () => ({
  triggerHaptic: vi.fn()
}))

vi.mock('./profile-scope', () => ({
  SettingsProfileScope: () => null
}))

import { MessageKeysSetting } from './message-keys-setting'

describe('MessageKeysSetting', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    requestGatewayMock.mockImplementation((_conn, _prof, method, params) => {
      if (method === 'message_keys.list') {
        return Promise.resolve({
          items: [
            { id: 'key-test-1234', name: 'my-bot', created_at: '2026-09-25T10:00:00Z' }
          ]
        })
      }

      if (method === 'message_keys.get_policy') {
        return Promise.resolve({ require_chat_key: false })
      }

      if (method === 'message_keys.set_policy') {
        return Promise.resolve({ require_chat_key: params?.require_chat_key })
      }

      if (method === 'message_keys.create') {
        return Promise.resolve({
          id: 'key-new-5678',
          name: params?.name,
          created_at: '2026-09-25T11:00:00Z',
          key: 'hmmsg_plaintext_secret_xyz'
        })
      }

      if (method === 'message_keys.revoke') {
        return Promise.resolve({ ok: true, removed: true })
      }

      return Promise.reject(new Error(`Unknown method: ${method}`))
    })
  })

  afterEach(() => {
    cleanup()
  })

  it('loads message keys and policy on mount', async () => {
    render(<MessageKeysSetting />)

    await waitFor(() => {
      expect(screen.getByText('my-bot')).toBeDefined()
    })

    expect(requestGatewayMock).toHaveBeenCalledWith(
      'test-conn',
      'default',
      'message_keys.list',
      {},
      undefined,
      undefined,
      expect.anything()
    )
    expect(requestGatewayMock).toHaveBeenCalledWith(
      'test-conn',
      'default',
      'message_keys.get_policy',
      {},
      undefined,
      undefined,
      expect.anything()
    )
  })

  it('toggles require_chat_key policy', async () => {
    render(<MessageKeysSetting />)

    await waitFor(() => {
      expect(screen.getByText('Require Chat API Key')).toBeDefined()
    })

    const switchBtn = screen.getByRole('switch')
    fireEvent.click(switchBtn)

    await waitFor(() => {
      expect(requestGatewayMock).toHaveBeenCalledWith(
        'test-conn',
        'default',
        'message_keys.set_policy',
        { require_chat_key: true },
        undefined,
        undefined,
        expect.anything()
      )
    })
  })

  it('creates a new key and renders one-time secret', async () => {
    render(<MessageKeysSetting />)

    await waitFor(() => {
      expect(screen.getByText('Create Key')).toBeDefined()
    })

    fireEvent.click(screen.getByText('Create Key'))

    const input = screen.getByPlaceholderText('e.g. openclaw-gateway, router-node')
    fireEvent.change(input, { target: { value: 'remote-cluster' } })

    const createBtn = screen.getAllByRole('button', { name: /create/i }).pop()!
    fireEvent.click(createBtn)

    await waitFor(() => {
      expect(screen.getByText('Copy Your New Message Key')).toBeDefined()
      expect(screen.getByDisplayValue('hmmsg_plaintext_secret_xyz')).toBeDefined()
    })

    // Clicking done dismisses the secret
    fireEvent.click(screen.getByRole('button', { name: /done/i }))
    await waitFor(() => {
      expect(screen.queryByText('Copy Your New Message Key')).toBeNull()
    })
  })

  it('revokes a key upon confirmation', async () => {
    render(<MessageKeysSetting />)

    await waitFor(() => {
      expect(screen.getByText('my-bot')).toBeDefined()
    })

    const buttons = screen.getAllByRole('button')
    // Click trash button next to key
    const trashBtn = buttons.find(b => b.className.includes('text-destructive'))
    expect(trashBtn).toBeDefined()
    fireEvent.click(trashBtn!)

    await waitFor(() => {
      expect(screen.getByText('Revoke Message Key')).toBeDefined()
    })

    const confirmBtn = screen.getByRole('button', { name: 'Revoke' })
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(requestGatewayMock).toHaveBeenCalledWith(
        'test-conn',
        'default',
        'message_keys.revoke',
        { id: 'key-test-1234' },
        undefined,
        undefined,
        expect.anything()
      )
      expect(screen.queryByText('my-bot')).toBeNull()
    })
  })

  it('immediately clears one-time plaintext key when switching profile, and does not restore it on switch back (S3)', async () => {
    testScopeProfile.set('default')
    render(<MessageKeysSetting />)

    await waitFor(() => {
      expect(screen.getByText('Create Key')).toBeDefined()
    })

    fireEvent.click(screen.getByText('Create Key'))
    const input = screen.getByPlaceholderText('e.g. openclaw-gateway, router-node')
    fireEvent.change(input, { target: { value: 'ephemeral-node' } })

    const createBtn = screen.getAllByRole('button', { name: /create/i }).pop()!
    fireEvent.click(createBtn)

    await waitFor(() => {
      expect(screen.getByText('Copy Your New Message Key')).toBeDefined()
      expect(screen.getByDisplayValue('hmmsg_plaintext_secret_xyz')).toBeDefined()
    })

    // Switch profile to profile-b
    await act(async () => {
      testScopeProfile.set('profile-b')
    })

    // Assert plaintext key is immediately hidden
    expect(screen.queryByText('Copy Your New Message Key')).toBeNull()
    expect(screen.queryByDisplayValue('hmmsg_plaintext_secret_xyz')).toBeNull()

    // Switch back to default profile
    await act(async () => {
      testScopeProfile.set('default')
    })

    // Plaintext key MUST NOT be restored
    expect(screen.queryByText('Copy Your New Message Key')).toBeNull()
    expect(screen.queryByDisplayValue('hmmsg_plaintext_secret_xyz')).toBeNull()
  })

  it('prevents stale profile response from polluting newly selected profile view (S4)', async () => {
    let resolveDefaultList: ((val: any) => void) | null = null

    const defaultListPromise = new Promise(resolve => {
      resolveDefaultList = resolve
    })

    requestGatewayMock.mockImplementation((_conn, prof, method) => {
      if (method === 'message_keys.list') {
        if (prof === 'slow-profile') {
          return defaultListPromise
        }

        return Promise.resolve({
          items: [{ id: 'key-fast', name: 'fast-profile-key', created_at: '2026-09-25T10:00:00Z' }]
        })
      }

      if (method === 'message_keys.get_policy') {
        return Promise.resolve({ require_chat_key: false })
      }

      return Promise.resolve({})
    })

    testScopeProfile.set('slow-profile')
    render(<MessageKeysSetting />)

    // Switch to fast-profile while slow-profile list request is still in flight
    await act(async () => {
      testScopeProfile.set('fast-profile')
    })

    await waitFor(() => {
      expect(screen.getByText('fast-profile-key')).toBeDefined()
    })

    // Now resolve the stale slow-profile response
    await act(async () => {
      resolveDefaultList!({
        items: [{ id: 'key-stale', name: 'stale-slow-key', created_at: '2026-09-25T09:00:00Z' }]
      })
    })

    // Stale slow-profile key must NOT appear or overwrite fast-profile view
    expect(screen.queryByText('stale-slow-key')).toBeNull()
    expect(screen.getByText('fast-profile-key')).toBeDefined()
  })
});
