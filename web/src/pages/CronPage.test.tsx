import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const {
  getCronJobs,
  getCronDeliveryTargets,
  getProfiles,
  getActiveProfile,
  getSkills,
  getToolsets,
  getModelOptions,
  getStatus,
} = vi.hoisted(() => ({
  getCronJobs: vi.fn(),
  getCronDeliveryTargets: vi.fn(),
  getProfiles: vi.fn(),
  getActiveProfile: vi.fn(),
  getSkills: vi.fn(),
  getToolsets: vi.fn(),
  getModelOptions: vi.fn(),
  getStatus: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getCronJobs,
    getCronDeliveryTargets,
    getProfiles,
    getActiveProfile,
    getSkills,
    getToolsets,
    getModelOptions,
    getStatus,
    createCronJob: vi.fn(),
    updateCronJob: vi.fn(),
    deleteCronJob: vi.fn(),
    pauseCronJob: vi.fn(),
    resumeCronJob: vi.fn(),
    triggerCronJob: vi.fn(),
  },
}));

import CronPage from "./CronPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <CronPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getProfiles.mockResolvedValue({ profiles: [] });
  getActiveProfile.mockResolvedValue({ active: "default", current: "default" });
  getCronDeliveryTargets.mockResolvedValue([]);
  getSkills.mockResolvedValue([]);
  getToolsets.mockResolvedValue([]);
  getModelOptions.mockResolvedValue(null);
  getStatus.mockResolvedValue({});
});

describe("CronPage localization", () => {
  it.each([
    [
      "zh",
      "已调度任务",
      "编辑任务",
    ],
    [
      "zh-hant",
      "已排程任務",
      "編輯任務",
    ],
  ])(
    "renders jobs and actions in %s without English fallback",
    async (locale, headerTitle, editJobAria) => {
      localStorage.setItem("hermes-locale", locale);
      getCronJobs.mockResolvedValue([
        {
          id: "job-1",
          name: "Morning briefing",
          prompt: "Summarize news",
          schedule: "0 9 * * *",
          state: "active",
          created_at: 1000,
          next_run_at: 2000,
          last_run_at: null,
        },
      ]);

      render(<TestWrapper />);

      expect(await screen.findByText(new RegExp(headerTitle))).toBeTruthy();
      expect(screen.getByRole("button", { name: editJobAria })).toBeTruthy();

      expect(screen.queryByText("Scheduled Jobs")).toBeNull();
      expect(screen.queryByRole("button", { name: "Edit job" })).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "暂无定时任务。在上方创建一个。",
    ],
    [
      "zh-hant",
      "尚未設定排程任務。請於上方建立。",
    ],
  ])(
    "renders empty state in %s",
    async (locale, emptyText) => {
      localStorage.setItem("hermes-locale", locale);
      getCronJobs.mockResolvedValue([]);

      render(<TestWrapper />);

      expect(await screen.findByText(emptyText)).toBeTruthy();
      expect(screen.queryByText("No scheduled jobs")).toBeNull();
    },
  );
});
