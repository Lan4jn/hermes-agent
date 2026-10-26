import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ReactNode, useMemo, useState } from "react";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getSkills, getToolsets, getSkillHubSources, getSkillHubTrending } = vi.hoisted(() => ({
  getSkills: vi.fn(),
  getToolsets: vi.fn(),
  getSkillHubSources: vi.fn(),
  getSkillHubTrending: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getSkills,
    getToolsets,
    getSkillHubSources,
    getSkillHubTrending,
    toggleSkill: vi.fn(),
    createSkill: vi.fn(),
    updateSkill: vi.fn(),
    deleteSkill: vi.fn(),
  },
}));

import SkillsPage from "./SkillsPage";

function TestWrapper() {
  const [headerEnd, setHeaderEnd] = useState<ReactNode>(null);
  const [headerAfterTitle, setHeaderAfterTitle] = useState<ReactNode>(null);
  const pageHeaderValue = useMemo(
    () => ({
      setEnd: setHeaderEnd,
      setAfterTitle: setHeaderAfterTitle,
      setTitle: vi.fn(),
    }),
    [],
  );

  return (
    <MemoryRouter>
      <I18nProvider>
        <PageHeaderContext.Provider value={pageHeaderValue}>
          <div data-testid="header-after-title">{headerAfterTitle}</div>
          <div data-testid="header-end">{headerEnd}</div>
          <SkillsPage />
        </PageHeaderContext.Provider>
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getSkills.mockReset();
  getToolsets.mockReset();
  getSkillHubSources.mockReset();
  getSkillHubTrending.mockReset();
});

describe("SkillsPage localization", () => {
  it.each([
    [
      "zh",
      "全部 (1)",
      "工具集 (1)",
      "浏览技能中心",
      /已启用 1\/1/,
      "学习技能",
    ],
    [
      "zh-hant",
      "全部 (1)",
      "工具集 (1)",
      "瀏覽技能中心",
      /已啟用 1\/1/,
      "學習技能",
    ],
  ])(
    "renders normal skills state in %s without English fallback",
    async (locale, allLabel, toolsetsLabel, browseHubLabel, enabledRegex, learnBtnText) => {
      localStorage.setItem("hermes-locale", locale);
      getSkills.mockResolvedValue([
        {
          name: "weather-skill",
          description: "Fetches live weather reports",
          enabled: true,
          category: "utilities",
        },
      ]);
      getToolsets.mockResolvedValue([
        {
          name: "web-tools",
          description: "Web search and scrape",
          enabled: true,
        },
      ]);
      getSkillHubSources.mockResolvedValue([]);
      getSkillHubTrending.mockResolvedValue([]);

      render(<TestWrapper />);

      expect(await screen.findByText(allLabel)).toBeTruthy();
      expect(screen.getByText(toolsetsLabel)).toBeTruthy();
      expect(screen.getByText(browseHubLabel)).toBeTruthy();
      expect(await screen.findByText(enabledRegex)).toBeTruthy();
      expect(screen.getByRole("button", { name: learnBtnText })).toBeTruthy();

      expect(screen.queryByText("Browse hub")).toBeNull();
      expect(screen.queryByText("All (1)")).toBeNull();
      expect(screen.queryByText("Learn a skill")).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      /未找到技能/,
      "全部 (0)",
    ],
    [
      "zh-hant",
      /找不到技能/,
      "全部 (0)",
    ],
  ])(
    "renders empty skills state in %s",
    async (locale, emptyRegex, allEmptyLabel) => {
      localStorage.setItem("hermes-locale", locale);
      getSkills.mockResolvedValue([]);
      getToolsets.mockResolvedValue([]);
      getSkillHubSources.mockResolvedValue([]);
      getSkillHubTrending.mockResolvedValue([]);

      render(<TestWrapper />);

      expect(await screen.findByText(allEmptyLabel)).toBeTruthy();
      expect(screen.getByText(emptyRegex)).toBeTruthy();
      expect(screen.queryByText("No skills found")).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "学习技能",
      "开始学习",
    ],
    [
      "zh-hant",
      "學習技能",
      "開始學習",
    ],
  ])(
    "renders Learn Modal in %s",
    async (locale, learnBtnText, submitText) => {
      localStorage.setItem("hermes-locale", locale);
      getSkills.mockResolvedValue([
        {
          name: "skill-1",
          description: "test",
          enabled: true,
          category: "general",
        },
      ]);
      getToolsets.mockResolvedValue([]);
      getSkillHubSources.mockResolvedValue([]);
      getSkillHubTrending.mockResolvedValue([]);

      render(<TestWrapper />);

      // Open the learn dialog via "Learn a skill" button
      const openBtn = await screen.findByRole("button", { name: learnBtnText });
      fireEvent.click(openBtn);

      expect(await screen.findByRole("button", { name: submitText })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Start Learning" })).toBeNull();
    },
  );
});
