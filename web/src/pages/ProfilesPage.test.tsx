import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ReactNode, useMemo, useState } from "react";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getProfiles, getActiveProfile, getProfileSoul } = vi.hoisted(() => ({
  getProfiles: vi.fn(),
  getActiveProfile: vi.fn(),
  getProfileSoul: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getProfiles,
    getActiveProfile,
    getProfileSoul,
    getModelChoices: vi.fn().mockResolvedValue([]),
    getModelOptions: vi.fn().mockResolvedValue([]),
    createProfile: vi.fn(),
    deleteProfile: vi.fn(),
    renameProfile: vi.fn(),
    setActiveProfile: vi.fn(),
    updateProfileDescription: vi.fn(),
    describeProfileAuto: vi.fn(),
    setProfileModel: vi.fn(),
    getProfileSetupCommand: vi.fn(),
  },
}));

import ProfilesPage from "./ProfilesPage";

function TestWrapper() {
  const [headerEnd, setHeaderEnd] = useState<ReactNode>(null);
  const pageHeaderValue = useMemo(
    () => ({
      setEnd: setHeaderEnd,
      setAfterTitle: vi.fn(),
      setTitle: vi.fn(),
    }),
    [],
  );

  return (
    <MemoryRouter>
      <I18nProvider>
        <PageHeaderContext.Provider value={pageHeaderValue}>
          <div data-testid="header-end">{headerEnd}</div>
          <ProfilesPage />
        </PageHeaderContext.Provider>
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
  getProfiles.mockReset();
  getActiveProfile.mockReset();
  getProfileSoul.mockReset();
});

describe("ProfilesPage localization", () => {
  it.each([
    [
      "zh",
      "多Agent配置列表 (1)",
      "活跃配置档案",
      "向导构建",
      "新建多Agent配置",
    ],
    [
      "zh-hant",
      "設定檔 (1)",
      "活躍配置檔案",
      "精靈建構",
      "新增設定檔",
    ],
  ])(
    "renders profile list and header actions in %s without English fallback",
    async (locale, listTitle, activeBanner, buildBtnText, newProfileTitle) => {
      localStorage.setItem("hermes-locale", locale);
      getProfiles.mockResolvedValue({
        profiles: [
          {
            name: "default",
            description: "Default profile",
            is_default: true,
            has_env: true,
          },
        ],
      });
      getActiveProfile.mockResolvedValue({
        active: "default",
        current: "default",
      });

      render(<TestWrapper />);

      expect(await screen.findByText(listTitle)).toBeTruthy();
      expect(screen.getByText(new RegExp(activeBanner))).toBeTruthy();
      expect(await screen.findByRole("button", { name: buildBtnText })).toBeTruthy();

      expect(screen.queryByText("All profiles (1)")).toBeNull();
      expect(screen.queryByRole("button", { name: "Build" })).toBeNull();

      // Open quick create modal
      const createBtn = screen.getByRole("button", { name: /创建|建立/ });
      fireEvent.click(createBtn);

      expect(await screen.findByRole("heading", { name: newProfileTitle })).toBeTruthy();
      expect(screen.queryByText("New Profile")).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "暂无多Agent配置。",
    ],
    [
      "zh-hant",
      "找不到設定檔。",
    ],
  ])(
    "renders empty state in %s",
    async (locale, emptyText) => {
      localStorage.setItem("hermes-locale", locale);
      getProfiles.mockResolvedValue({ profiles: [] });
      getActiveProfile.mockResolvedValue(null);

      render(<TestWrapper />);

      expect(await screen.findByText(emptyText)).toBeTruthy();
      expect(screen.queryByText("No profiles found.")).toBeNull();
    },
  );
});
