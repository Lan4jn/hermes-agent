import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const {
  getStatus,
  getModelOptions,
  getMoaConfig,
  getAuxiliaryTasks,
  getProviders,
  getAnalyticsStatus,
  getModelsAnalytics,
} = vi.hoisted(() => ({
  getStatus: vi.fn(),
  getModelOptions: vi.fn(),
  getMoaConfig: vi.fn(),
  getAuxiliaryTasks: vi.fn(),
  getProviders: vi.fn(),
  getAnalyticsStatus: vi.fn(),
  getModelsAnalytics: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getStatus,
    getModelOptions,
    getMoaConfig,
    getMoaModels: vi.fn().mockResolvedValue(null),
    getConfig: vi.fn().mockResolvedValue({}),
    getModelsAnalytics,
    getAuxiliaryModels: vi.fn().mockResolvedValue({
      main: { provider: "anthropic", model: "claude-3-5-sonnet" },
      tasks: [],
    }),
    getAuxiliaryTasks,
    getProviders,
    getAnalyticsStatus,
    setModelAssignment: vi.fn(),
  },
}));

import ModelsPage from "./ModelsPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <ModelsPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getModelsAnalytics.mockResolvedValue({
    totals: {
      distinct_models: 1,
      total_tokens: 1000,
      estimated_cost_usd: 0.05,
    },
    models: [],
    by_model: [],
  });
  getStatus.mockResolvedValue({
    model: "claude-3-5-sonnet",
    model_provider: "anthropic",
  });
  getModelOptions.mockResolvedValue({
    providers: [
      {
        id: "anthropic",
        name: "Anthropic",
        models: [{ id: "claude-3-5-sonnet", name: "Claude 3.5 Sonnet" }],
      },
    ],
  });
  getMoaConfig.mockResolvedValue({
    enabled: false,
    default_preset: "default",
    presets: {},
  });
  getAuxiliaryTasks.mockResolvedValue({ tasks: [] });
  getProviders.mockResolvedValue([]);
  getAnalyticsStatus.mockResolvedValue({ enabled: false });
});

describe("ModelsPage localization", () => {
  it.each([
    [
      "zh",
      "模型设置",
      "当前主模型",
      "辅助任务覆盖",
    ],
    [
      "zh-hant",
      "模型設定",
      "當前主模型",
      "輔助任務覆蓋",
    ],
  ])(
    "renders localized models section in %s without English fallback",
    async (locale, title, mainModelLabel, auxTasksLabel) => {
      localStorage.setItem("hermes-locale", locale);

      render(<TestWrapper />);

      expect(await screen.findByText(title)).toBeTruthy();
      expect(screen.getByText(mainModelLabel)).toBeTruthy();
      expect(screen.getByText(auxTasksLabel)).toBeTruthy();

      expect(screen.queryByText("Model Settings")).toBeNull();
      expect(screen.queryByText("Current Main Model")).toBeNull();
      expect(screen.queryByText("Auxiliary tasks")).toBeNull();
    },
  );
});
