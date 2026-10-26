import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

vi.mock("@/lib/api", () => ({
  api: {
    createProfile: vi.fn(),
    getModelOptions: vi.fn().mockResolvedValue([]),
    getSkills: vi.fn().mockResolvedValue([]),
    searchSkillHub: vi.fn().mockResolvedValue([]),
  },
}));

import ProfileBuilderPage from "./ProfileBuilderPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <ProfileBuilderPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
});

describe("ProfileBuilderPage localization", () => {
  it.each([
    [
      "zh",
      "配置档案构建向导",
      "配置档案名称",
      "下一步",
      "仅允许小写字母、数字、短横线和下划线；首字符必须是字母或数字。",
    ],
    [
      "zh-hant",
      "配置檔案構建嚮導",
      "配置檔案名稱",
      "下一步",
      "僅允許小寫字母、數字、連字號與底線；首字元必須是字母或數字。",
    ],
  ])(
    "renders step 1 and validates name rule in %s without English fallback",
    async (locale, heading, nameLabel, nextBtnText, ruleText) => {
      localStorage.setItem("hermes-locale", locale);

      render(<TestWrapper />);

      expect(await screen.findByRole("heading", { name: heading })).toBeTruthy();
      expect(screen.getByLabelText(nameLabel)).toBeTruthy();
      expect(screen.getByRole("button", { name: nextBtnText })).toBeTruthy();

      expect(screen.queryByText("Profile Builder")).toBeNull();
      expect(screen.queryByText("Profile name")).toBeNull();

      // Type invalid name to trigger rule error
      const input = screen.getByLabelText(nameLabel);
      fireEvent.change(input, { target: { value: "INVALID NAME!" } });

      expect(await screen.findByText(ruleText)).toBeTruthy();
      expect(
        screen.queryByText(
          "Lowercase letters, digits, hyphens and underscores; must start with a letter or digit.",
        ),
      ).toBeNull();
    },
  );
});
