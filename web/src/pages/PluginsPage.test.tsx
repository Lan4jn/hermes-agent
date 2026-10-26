import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { getPluginsHub, getPluginsCatalog } = vi.hoisted(() => ({
  getPluginsHub: vi.fn(),
  getPluginsCatalog: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getPluginsHub,
    getPluginsCatalog,
    installAgentPlugin: vi.fn(),
    rescanPlugins: vi.fn(),
    setMemoryProvider: vi.fn(),
    updateMemoryProviderConfig: vi.fn(),
    setupMemoryProvider: vi.fn(),
    savePluginProviders: vi.fn(),
    disableAgentPlugin: vi.fn(),
    enableAgentPlugin: vi.fn(),
    updateAgentPlugin: vi.fn(),
    setPluginVisibility: vi.fn(),
    removeAgentPlugin: vi.fn(),
  },
}));

import PluginsPage from "./PluginsPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <PluginsPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getPluginsHub.mockResolvedValue({
    plugins: [],
    providers: {
      memory_provider: "",
      memory_options: [],
      context_engine: "compressor",
      context_options: [],
    },
    context_engines: [],
    memory_providers: [],
  });
  getPluginsCatalog.mockResolvedValue({
    entries: [],
    removed: [],
  });
});

describe("PluginsPage localization", () => {
  it.each([
    [
      "zh",
      "已安装插件",
      "插件目录",
      "记忆提供方",
    ],
    [
      "zh-hant",
      "已安裝的外掛",
      "外掛目錄",
      "記憶提供者",
    ],
  ])(
    "renders localized sections in %s without English fallback",
    async (locale, installedTitle, catalogTitle, memoryLabel) => {
      localStorage.setItem("hermes-locale", locale);

      render(<TestWrapper />);

      expect(await screen.findByText(installedTitle)).toBeTruthy();
      expect(screen.getByText(catalogTitle)).toBeTruthy();
      expect(screen.getByText(memoryLabel)).toBeTruthy();

      expect(screen.queryByText("Installed plugins")).toBeNull();
      expect(screen.queryByText("Plugin catalog")).toBeNull();
      expect(screen.queryByText("Memory provider")).toBeNull();
    },
  );
});
