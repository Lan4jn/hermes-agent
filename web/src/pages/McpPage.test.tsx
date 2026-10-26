import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ReactNode, useMemo, useState } from "react";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getMcpServers, getMcpCatalog, testMcpServer } = vi.hoisted(() => ({
  getMcpServers: vi.fn(),
  getMcpCatalog: vi.fn(),
  testMcpServer: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getMcpServers,
    getMcpCatalog,
    testMcpServer,
    addMcpServer: vi.fn(),
    removeMcpServer: vi.fn(),
    setMcpServerEnabled: vi.fn(),
    installMcpCatalogEntry: vi.fn(),
  },
}));

import McpPage from "./McpPage";

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
    <I18nProvider>
      <PageHeaderContext.Provider value={pageHeaderValue}>
        <div data-testid="header-end">{headerEnd}</div>
        <McpPage />
      </PageHeaderContext.Provider>
    </I18nProvider>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getMcpServers.mockReset();
  getMcpCatalog.mockReset();
});

describe("McpPage localization", () => {
  it.each([
    ["zh", "已配置的 MCP 服务器 (0)", "尚未配置任何 MCP 服务器。"],
    ["zh-hant", "已配置的 MCP 伺服器 (0)", "尚未配置任何 MCP 伺服器。"],
  ])("renders empty state in %s without English fallback", async (locale, title, empty) => {
    localStorage.setItem("hermes-locale", locale);
    getMcpServers.mockResolvedValue({ servers: [] });
    getMcpCatalog.mockResolvedValue({ entries: [], diagnostics: [] });

    render(<TestWrapper />);

    expect(await screen.findByText(title)).toBeTruthy();
    expect(
      screen.getByText((_, element) =>
        element?.tagName === "P" && Boolean(element.textContent?.includes(empty)),
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Your MCP servers (0)")).toBeNull();
    expect(screen.queryByText("No MCP servers configured.")).toBeNull();
  });

  it.each([
    [
      "zh",
      "已配置的 MCP 服务器 (1)",
      "服务目录 (1)",
      "禁用",
      "测试连接",
      "删除",
      "安装",
    ],
    [
      "zh-hant",
      "已配置的 MCP 伺服器 (1)",
      "服務目錄 (1)",
      "禁用",
      "測試連線",
      "刪除",
      "安裝",
    ],
  ])(
    "renders normal state with servers and catalog in %s",
    async (locale, serversTitle, catalogTitle, disableBtn, testBtn, deleteBtn, installBtn) => {
      localStorage.setItem("hermes-locale", locale);
      getMcpServers.mockResolvedValue({
        servers: [
          {
            name: "test-server",
            transport: "http",
            url: "https://mcp.example.com",
            enabled: true,
          },
        ],
      });
      getMcpCatalog.mockResolvedValue({
        entries: [
          {
            name: "catalog-server",
            transport: "stdio",
            command: "npx",
            args: ["cat"],
            description: "Catalog item",
            source: "official",
            installed: false,
            enabled: false,
            auth_type: "none",
            required_env: [],
            bootstrap: [],
          },
        ],
        diagnostics: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(serversTitle)).toBeTruthy();
      expect(screen.getByText(catalogTitle)).toBeTruthy();

      expect(screen.getByRole("button", { name: disableBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: testBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: deleteBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: installBtn })).toBeTruthy();

      expect(screen.queryByText("Your MCP servers (1)")).toBeNull();
      expect(screen.queryByRole("button", { name: "Test connection" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
    },
  );

  it.each([
    ["zh", "MCP 服务器失败：network error"],
    ["zh-hant", "MCP 伺服器失敗：network error"],
  ])("renders error state when server loading fails in %s", async (locale, errorMsg) => {
    localStorage.setItem("hermes-locale", locale);
    getMcpServers.mockRejectedValue(new Error("network error"));
    getMcpCatalog.mockResolvedValue({ entries: [], diagnostics: [] });

    render(<TestWrapper />);

    expect(await screen.findByText(errorMsg)).toBeTruthy();
    expect(screen.queryByText("Could not load MCP servers: network error")).toBeNull();
  });

  it.each([
    [
      "zh",
      "添加服务器",
      "添加 MCP 服务器",
      "保存在此 Profile 的 .env 中；config.yaml 仅保留环境变量引用。",
    ],
    [
      "zh-hant",
      "新增伺服器",
      "新增 MCP 伺服器",
      "儲存在此 Profile 的 .env 中；config.yaml 僅保留環境變數引用。",
    ],
  ])(
    "renders Add Server modal with localized help text in %s",
    async (locale, addServerBtn, modalTitle, bearerHelp) => {
      localStorage.setItem("hermes-locale", locale);
      getMcpServers.mockResolvedValue({ servers: [] });
      getMcpCatalog.mockResolvedValue({ entries: [], diagnostics: [] });

      render(<TestWrapper />);

      // The header button should be rendered via header portal/setEnd
      const openBtn = await screen.findByRole("button", { name: addServerBtn });
      fireEvent.click(openBtn);

      expect(await screen.findByText(modalTitle)).toBeTruthy();

      // Switch auth to header to see bearerTokenHelp
      const modal = (await screen.findByText(modalTitle)).closest("[role='dialog']")!;
      const authTrigger = modal.querySelector("#mcp-auth button[role='combobox']")!;
      fireEvent.click(authTrigger);
      const headerOption = await screen.findByRole("option", { name: /Bearer (?:令牌|token)/i });
      fireEvent.click(headerOption);

      expect(await screen.findByText(bearerHelp)).toBeTruthy();
      expect(
        screen.queryByText("Stored in this profile's .env; config.yaml keeps only an environment-variable reference."),
      ).toBeNull();
    },
  );
});
