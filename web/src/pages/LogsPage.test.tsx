import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { getLogs } = vi.hoisted(() => ({
  getLogs: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getLogs,
  },
}));

import LogsPage from "./LogsPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <LogsPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
});

describe("LogsPage localization", () => {
  it.each([
    [
      "zh",
      "文件",
      "级别",
      "组件",
      "行数",
      "未找到日志记录",
    ],
    [
      "zh-hant",
      "檔案",
      "層級",
      "元件",
      "行數",
      "找不到日誌記錄",
    ],
  ])(
    "renders filter labels and empty state in %s without English fallback",
    async (
      locale,
      fileFilter,
      levelFilter,
      componentFilter,
      linesFilter,
      noLogsText,
    ) => {
      localStorage.setItem("hermes-locale", locale);
      getLogs.mockResolvedValue({
        lines: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(noLogsText)).toBeTruthy();
      expect(screen.getByText(fileFilter)).toBeTruthy();
      expect(screen.getByText(levelFilter)).toBeTruthy();
      expect(screen.getByText(componentFilter)).toBeTruthy();
      expect(screen.getByText(linesFilter)).toBeTruthy();

      expect(screen.queryByText("No log entries found")).toBeNull();
      expect(screen.queryByText("File")).toBeNull();
      expect(screen.queryByText("Level")).toBeNull();
      expect(screen.queryByText("Component")).toBeNull();
      expect(screen.queryByText("Lines")).toBeNull();
    },
  );
});
