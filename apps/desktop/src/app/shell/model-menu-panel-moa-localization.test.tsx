import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

import { DropdownMenu, DropdownMenuContent } from '@/components/ui/dropdown-menu'
import { I18nProvider } from '@/i18n/context'
import { $activeSessionId, $currentModel, $currentProvider } from '@/store/session'

import { ModelMenuPanel } from './model-menu-panel'

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
  Element.prototype.hasPointerCapture = vi.fn(() => false)
  Element.prototype.releasePointerCapture = vi.fn()
})

const getGlobalModelOptions = vi.fn()

vi.mock('@/hermes', () => ({
  getGlobalModelOptions: (...args: unknown[]) => getGlobalModelOptions(...args),
  setApiRequestProfile: vi.fn(),
  getHermesConfigRecord: vi.fn().mockResolvedValue({}),
  saveHermesConfig: vi.fn().mockResolvedValue({ ok: true })
}))

const MOA_PROVIDER = { models: ['default', 'BeastMode'], name: 'Mixture of Agents', slug: 'moa' }

beforeEach(() => {
  $activeSessionId.set('runtime-1')
  $currentModel.set('')
  $currentProvider.set('')
  getGlobalModelOptions.mockResolvedValue({ providers: [MOA_PROVIDER] })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderPanelWithLocale(locale: 'en' | 'zh' | 'zh-hant') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  const requestGateway = vi.fn(async (method: string) => {
    if (method === 'model.options') {
      return getGlobalModelOptions()
    }

    throw new Error(`unexpected gateway method: ${method}`)
  })

  return render(
    <I18nProvider configClient={null} initialLocale={locale}>
      <QueryClientProvider client={client}>
        <DropdownMenu open>
          <DropdownMenuContent>
            <ModelMenuPanel
              onSelectModel={vi.fn()}
              requestGateway={requestGateway as never}
            />
          </DropdownMenuContent>
        </DropdownMenu>
      </QueryClientProvider>
    </I18nProvider>
  )
}

describe('ModelMenuPanel MoA presets localization', () => {
  it.each([
    ['en', 'MoA presets'],
    ['zh', 'MoA 预设'],
    ['zh-hant', 'MoA 預設']
  ] as const)('renders localized MoA presets section title in %s', async (locale, expectedTitle) => {
    const { findByText } = renderPanelWithLocale(locale)
    await findByText('MoA: BeastMode')

    // eslint-disable-next-line no-restricted-globals
    expect(document.body.textContent).toContain(expectedTitle)

    if (locale !== 'en') {
      // eslint-disable-next-line no-restricted-globals
      expect(document.body.textContent).not.toContain('MoA presets')
    }
  })
})
