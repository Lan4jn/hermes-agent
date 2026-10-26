// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { TRANSLATIONS } from '@/i18n/catalog'
import { stubResizeObserver } from '@/test/jsdom'

stubResizeObserver()

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false
    }
  }
})

vi.mock('@/hermes', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    deleteEnvVar: vi.fn(),
    getEnvVars: vi.fn().mockResolvedValue({}),
    getHermesConfigDefaults: vi.fn().mockResolvedValue({}),
    getHermesConfigRecord: vi.fn().mockResolvedValue({}),
    getElevenLabsVoices: vi.fn().mockResolvedValue([]),
    getProfiles: vi.fn().mockResolvedValue({ profiles: [] }),
    revealEnvVar: vi.fn(),
    saveHermesConfig: vi.fn().mockResolvedValue({ ok: true }),
    setApiRequestProfile: vi.fn(),
    setEnvVar: vi.fn()
  }
})

vi.mock('@/store/session', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    $connection: {
      get: () => ({ kind: 'local' }),
      listen: () => () => {},
      subscribe: (fn: any) => {
        fn({ kind: 'local' })

        return () => {}
      }
    },
    $gatewayState: {
      get: () => 'open',
      listen: () => () => {},
      subscribe: (fn: any) => {
        fn('open')

        return () => {}
      }
    }
  }
})

vi.mock('@/store/gateway', async importOriginal => {
  const actual = await importOriginal<any>()

  return {
    ...actual,
    requestGatewayForAgent: (_conn: any, _prof: any, method: string) => {
      if (method === 'message_keys.list') {return Promise.resolve({ items: [] })}

      if (method === 'message_keys.get_policy') {return Promise.resolve({ require_chat_key: false })}

      return Promise.resolve({})
    }
  }
})

import { SettingsView } from './index'

describe('Settings Navigation Localization (S5)', () => {
  beforeEach(() => {
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn()
    })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('declares localized navigation labels for message keys in translations catalog', () => {
    expect(TRANSLATIONS.zh.settings.nav.keysMessage).toBe('消息密钥')
    expect(TRANSLATIONS.en.settings.nav.keysMessage).toBe('Message Keys')
    expect(TRANSLATIONS['zh-hant'].settings.nav.keysMessage).toBe('訊息金鑰')
  })

  it('renders localized navigation in Chinese without hardcoded English label', async () => {
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nProvider configClient={null} initialLocale="zh">
            <MemoryRouter initialEntries={['/settings?tab=keys&kview=message']}>
              <SettingsView onClose={vi.fn()} />
            </MemoryRouter>
          </I18nProvider>
        </QueryClientProvider>
      )
    })

    // Navigation sub-item for message keys must render Chinese
    const zhItems = await screen.findAllByText('消息密钥')
    expect(zhItems.length).toBeGreaterThanOrEqual(1)
    // It should not have bare English navigation item
    expect(screen.queryByRole('button', { name: 'Message Keys' })).toBeNull()
  })

  it('renders localized navigation in Traditional Chinese without hardcoded English label', async () => {
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nProvider configClient={null} initialLocale="zh-hant">
            <MemoryRouter initialEntries={['/settings?tab=keys&kview=message']}>
              <SettingsView onClose={vi.fn()} />
            </MemoryRouter>
          </I18nProvider>
        </QueryClientProvider>
      )
    })

    const zhHantItems = await screen.findAllByText('訊息金鑰')
    expect(zhHantItems.length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByRole('button', { name: 'Message Keys' })).toBeNull()
  })

  it.each([
    ['zh', '网关', '关于', '键盘快捷键'],
    ['zh-hant', '閘道', '關於', '鍵盤快捷鍵']
  ] as const)('renders top-level settings navigation in %s', async (locale, gatewayLabel, aboutLabel, keybindsLabel) => {
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nProvider configClient={null} initialLocale={locale}>
            <MemoryRouter initialEntries={['/settings']}>
              <SettingsView onClose={vi.fn()} />
            </MemoryRouter>
          </I18nProvider>
        </QueryClientProvider>
      )
    })

    expect(await screen.findByRole('button', { name: gatewayLabel })).toBeTruthy()
    expect(screen.getByRole('button', { name: aboutLabel })).toBeTruthy()
    expect(screen.getByRole('button', { name: keybindsLabel })).toBeTruthy()

    expect(screen.queryByRole('button', { name: 'Gateway' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'About' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Keybinds' })).toBeNull()
  })

  it('renders localized navigation in English', async () => {
    await act(async () => {
      render(
        <QueryClientProvider client={queryClient}>
          <I18nProvider configClient={null} initialLocale="en">
            <MemoryRouter initialEntries={['/settings?tab=keys&kview=message']}>
              <SettingsView onClose={vi.fn()} />
            </MemoryRouter>
          </I18nProvider>
        </QueryClientProvider>
      )
    })

    const enItems = await screen.findAllByText('Message Keys')
    expect(enItems.length).toBeGreaterThanOrEqual(1)
  })
})
