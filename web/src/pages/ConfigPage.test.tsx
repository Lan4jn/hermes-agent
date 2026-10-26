import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { getConfig, getSchema, getDefaults, getConfigRaw, getStatus } = vi.hoisted(
  () => ({
    getConfig: vi.fn(),
    getSchema: vi.fn(),
    getDefaults: vi.fn(),
    getConfigRaw: vi.fn(),
    getStatus: vi.fn(),
  }),
);

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getConfig,
    getSchema,
    getDefaults,
    getConfigRaw,
    getStatus,
    saveConfig: vi.fn(),
    saveConfigRaw: vi.fn(),
    getMessageKeys: vi.fn().mockResolvedValue([]),
    getMessagePolicy: vi.fn().mockResolvedValue({ require_chat_key: false }),
  },
}));

import ConfigPage from "./ConfigPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <ConfigPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getConfig.mockResolvedValue({});
  getSchema.mockResolvedValue({
    fields: {},
    category_order: ["general"],
  });
  getDefaults.mockResolvedValue({});
  getConfigRaw.mockResolvedValue({ path: "~/.hermes/config.yaml", raw: "" });
  getStatus.mockResolvedValue({ config_path: "~/.hermes/config.yaml" });
});

describe("ConfigPage localization", () => {
  it.each([
    [
      "zh",
      "分类",
      "导出配置为 JSON",
      "从 JSON 导入配置",
    ],
    [
      "zh-hant",
      "分類",
      "匯出設定為 JSON",
      "從 JSON 匯入設定",
    ],
  ])(
    "renders sections and header actions in %s without English fallback",
    async (locale, sectionsHeading, exportAria, importAria) => {
      localStorage.setItem("hermes-locale", locale);

      render(<TestWrapper />);

      expect(await screen.findByText(sectionsHeading)).toBeTruthy();
      expect(screen.getByRole("button", { name: exportAria })).toBeTruthy();
      expect(screen.getByRole("button", { name: importAria })).toBeTruthy();

      expect(screen.queryByText("Sections")).toBeNull();
      expect(screen.queryByRole("button", { name: "Export config" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Import config" })).toBeNull();
    },
  );
});
