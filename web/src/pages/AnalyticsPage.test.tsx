import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { getAnalytics, getConfig } = vi.hoisted(() => ({
  getAnalytics: vi.fn(),
  getConfig: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getAnalytics,
    getConfig,
  },
}));

import AnalyticsPage from "./AnalyticsPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <AnalyticsPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getAnalytics.mockResolvedValue({
    totals: {
      input_tokens: 100,
      output_tokens: 50,
      total_tokens: 150,
      total_sessions: 2,
      total_messages: 5,
    },
    daily: [
      {
        day: "2026-09-25",
        input_tokens: 100,
        output_tokens: 50,
        total_tokens: 150,
        sessions: 2,
      },
    ],
    by_model: [
      {
        model: "claude-3-7-sonnet",
        input_tokens: 100,
        output_tokens: 50,
        total_tokens: 150,
        sessions: 2,
      },
    ],
    skills: {
      top_skills: [
        {
          skill: "superpowers-tdd",
          view_count: 3,
          manage_count: 1,
          total_count: 4,
          last_used_at: "2026-09-25T12:00:00Z",
        },
      ],
    },
  });
});

describe("AnalyticsPage localization", () => {
  it.each([
    [
      "zh",
      "Token 分析已隐藏",
    ],
    [
      "zh-hant",
      "Token 分析已隱藏",
    ],
  ])(
    "renders hidden token analytics notice in %s without English fallback",
    async (locale, hiddenNotice) => {
      localStorage.setItem("hermes-locale", locale);
      getConfig.mockResolvedValue({
        dashboard: {
          show_token_analytics: false,
        },
      });

      render(<TestWrapper />);

      expect(await screen.findByText(hiddenNotice)).toBeTruthy();
      expect(screen.queryByText("Token analytics hidden")).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "每日 Token 用量",
      "每日明细",
      "模型用量明细",
      "常用技能",
    ],
    [
      "zh-hant",
      "每日 Token 用量",
      "每日明細",
      "各模型用量明細",
      "常用技能",
    ],
  ])(
    "renders analytics section titles when enabled in %s without English fallback",
    async (locale, dailyUsage, dailyBreakdown, modelBreakdown, topSkills) => {
      localStorage.setItem("hermes-locale", locale);
      getConfig.mockResolvedValue({
        dashboard: {
          show_token_analytics: true,
        },
      });

      render(<TestWrapper />);

      expect(await screen.findByText(dailyUsage)).toBeTruthy();
      expect(screen.getByText(dailyBreakdown)).toBeTruthy();
      expect(screen.getByText(modelBreakdown)).toBeTruthy();
      expect(screen.getByText(topSkills)).toBeTruthy();

      expect(screen.queryByText("Daily Token Usage")).toBeNull();
      expect(screen.queryByText("Daily Breakdown")).toBeNull();
      expect(screen.queryByText("Per-Model Breakdown")).toBeNull();
      expect(screen.queryByText("Top Skills")).toBeNull();
    },
  );
});
