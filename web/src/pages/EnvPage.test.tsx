import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { getEnvVars, getOAuthStatus } = vi.hoisted(() => ({
  getEnvVars: vi.fn(),
  getOAuthStatus: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getEnvVars,
    getOAuthStatus,
    getOAuthProviders: vi.fn().mockResolvedValue({ providers: [] }),
    setEnvVar: vi.fn(),
    deleteEnvVar: vi.fn(),
  },
}));

import EnvPage from "./EnvPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <EnvPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getOAuthStatus.mockResolvedValue([]);
});

describe("EnvPage localization", () => {
  it.each([
    [
      "zh",
      "LLM 提供商",
      "自定义密钥",
      "隐藏高级选项",
    ],
    [
      "zh-hant",
      "LLM 提供者",
      "自訂密鑰",
      "隱藏進階選項",
    ],
  ])(
    "renders cards and controls in %s without English fallback",
    async (locale, llmHeading, customHeading, advancedBtn) => {
      localStorage.setItem("hermes-locale", locale);
      getEnvVars.mockResolvedValue({
        vars: [],
        categories: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(llmHeading)).toBeTruthy();
      expect(screen.getByText(customHeading)).toBeTruthy();
      expect(screen.getByRole("button", { name: advancedBtn })).toBeTruthy();

      expect(screen.queryByText("LLM Providers")).toBeNull();
      expect(screen.queryByText("Custom Keys")).toBeNull();
      expect(screen.queryByRole("button", { name: "Hide advanced" })).toBeNull();
    },
  );
});
