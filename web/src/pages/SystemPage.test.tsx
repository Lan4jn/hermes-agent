import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";

const {
  getStatus,
  getSystemStats,
  getMemory,
  getCurator,
  getPortal,
  getHooks,
  getCheckpoints,
  getCredentialPool,
  getGatewayMigratePlan,
  checkHermesUpdate,
} = vi.hoisted(() => ({
  getStatus: vi.fn(),
  getSystemStats: vi.fn(),
  getMemory: vi.fn(),
  getCurator: vi.fn(),
  getPortal: vi.fn(),
  getHooks: vi.fn(),
  getCheckpoints: vi.fn(),
  getCredentialPool: vi.fn(),
  getGatewayMigratePlan: vi.fn(),
  checkHermesUpdate: vi.fn(),
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
    getSystemStats,
    getMemory,
    getCurator,
    getPortal,
    getHooks,
    getCheckpoints,
    getCredentialPool,
    getGatewayMigratePlan,
    checkHermesUpdate,
    cleanCache: vi.fn(),
    restartGateway: vi.fn(),
    reloadConfig: vi.fn(),
    runDoctor: vi.fn(),
    runSecurityAudit: vi.fn(),
  },
}));

import SystemPage from "./SystemPage";

function TestWrapper() {
  return (
    <MemoryRouter>
      <I18nProvider>
        <SystemPage />
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getMemory.mockResolvedValue({
    active: "",
    builtin_files: { memory: 1024, user: 2048 },
    providers: [],
  });
  getStatus.mockResolvedValue({
    status: "healthy",
    version: "1.0.0",
    gateway_state: "running",
    gateway: { uptime: 1234 },
  });
  getSystemStats.mockResolvedValue({
    os: "Windows",
    arch: "x64",
    hostname: "test-host",
    cpu_count: 8,
    memory: { total: 16000000000, used: 8000000000, percent: 50 },
    disk: { total: 500000000000, used: 200000000000, percent: 40 },
    uptime_seconds: 12345,
    psutil: true,
  });
  getCurator.mockResolvedValue({ enabled: false });
  getPortal.mockResolvedValue({ logged_in: false });
  getHooks.mockResolvedValue({ hooks: [] });
  getCheckpoints.mockResolvedValue({ sessions: [], total_bytes: 0 });
  getCredentialPool.mockResolvedValue({ providers: [] });
  getGatewayMigratePlan.mockResolvedValue({
    already_multiplexed: true,
    blockers: [],
    eligible: false,
  });
  checkHermesUpdate.mockResolvedValue({ update_available: false });
});

describe("SystemPage localization", () => {
  it.each([
    [
      "zh",
      "主机与系统",
      "运维操作",
      "安全审计",
      "全量备份",
    ],
    [
      "zh-hant",
      "主機與系統",
      "運維操作",
      "安全審計",
      "全量備份",
    ],
  ])(
    "renders localized sections in %s without English fallback",
    async (locale, hostTitle, operationsTitle, auditBtn, backupsLabel) => {
      localStorage.setItem("hermes-locale", locale);

      render(<TestWrapper />);

      expect(await screen.findByText(hostTitle)).toBeTruthy();
      expect(screen.getByText(operationsTitle)).toBeTruthy();
      expect(screen.getByText(auditBtn)).toBeTruthy();
      expect(screen.getByText(backupsLabel)).toBeTruthy();

      expect(screen.queryByText("Host")).toBeNull();
      expect(screen.queryByText("Operations")).toBeNull();
      expect(screen.queryByText("Security audit")).toBeNull();
      expect(screen.queryByText("Full backup")).toBeNull();
    },
  );
});
