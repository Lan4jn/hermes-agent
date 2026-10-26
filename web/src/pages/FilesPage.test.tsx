import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const { listFiles } = vi.hoisted(() => ({
  listFiles: vi.fn(),
}));

vi.mock("@/contexts/usePageHeader", () => ({
  usePageHeader: () => ({
    setEnd: vi.fn(),
    setAfterTitle: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    listFiles,
    uploadFile: vi.fn(),
    createFolder: vi.fn(),
    deleteFile: vi.fn(),
  },
}));

import FilesPage from "./FilesPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <FilesPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
});

describe("FilesPage localization", () => {
  it.each([
    [
      "zh",
      "上传文件",
      "新建文件夹",
      "此目录为空。",
      "名称",
      "大小",
      "修改时间",
      "操作",
    ],
    [
      "zh-hant",
      "上傳檔案",
      "新建資料夾",
      "此目錄為空。",
      "名稱",
      "大小",
      "修改時間",
      "操作",
    ],
  ])(
    "renders buttons and table in %s without English fallback",
    async (
      locale,
      uploadText,
      newFolderText,
      emptyDirText,
      nameHeader,
      sizeHeader,
      modHeader,
      actHeader,
    ) => {
      localStorage.setItem("hermes-locale", locale);
      listFiles.mockResolvedValue({
        path: "/workspace",
        can_upload: true,
        can_create_dir: true,
        entries: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(emptyDirText)).toBeTruthy();
      expect(screen.getAllByRole("button", { name: uploadText }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByRole("button", { name: newFolderText })).toBeTruthy();
      expect(screen.getByText(nameHeader)).toBeTruthy();
      expect(screen.getByText(sizeHeader)).toBeTruthy();
      expect(screen.getByText(modHeader)).toBeTruthy();
      expect(screen.getByText(actHeader)).toBeTruthy();

      expect(screen.queryByText("Upload files")).toBeNull();
      expect(screen.queryByText("New folder")).toBeNull();
      expect(screen.queryByText("This directory is empty.")).toBeNull();
      expect(screen.queryByText("Name")).toBeNull();
      expect(screen.queryByText("Size")).toBeNull();
      expect(screen.queryByText("Modified")).toBeNull();
      expect(screen.queryByText("Actions")).toBeNull();
    },
  );
});
