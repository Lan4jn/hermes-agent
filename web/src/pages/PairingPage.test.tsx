import { useMemo, useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getPairing } = vi.hoisted(() => ({
  getPairing: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getPairing,
    approvePairing: vi.fn(),
    revokePairing: vi.fn(),
    clearPendingPairing: vi.fn(),
  },
}));

import PairingPage from "./PairingPage";

function TestWrapper() {
  const [headerEnd, setHeaderEnd] = useState<React.ReactNode>(null);
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
          <PairingPage />
        </PageHeaderContext.Provider>
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
});

describe("PairingPage localization", () => {
  it.each([
    [
      "zh",
      "待审核申请 (1)",
      "已授权用户 (1)",
      "批准配对",
      "撤回授权",
      "清空待审核",
    ],
    [
      "zh-hant",
      "待稽核申請 (1)",
      "已授權使用者 (1)",
      "批准配對",
      "撤回授權",
      "清空待稽核",
    ],
  ])(
    "renders requests and actions in %s without English fallback",
    async (locale, pendingTitle, approvedTitle, approveBtn, revokeBtn, clearBtn) => {
      localStorage.setItem("hermes-locale", locale);
      getPairing.mockResolvedValue({
        pending: [
          {
            platform: "telegram",
            user_id: "user123",
            user_name: "Alice",
            request_id: "req-1",
            age_minutes: 5,
          },
        ],
        approved: [
          {
            platform: "discord",
            user_id: "user456",
            user_name: "Bob",
          },
        ],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(pendingTitle)).toBeTruthy();
      expect(screen.getByText(approvedTitle)).toBeTruthy();
      expect(screen.getByRole("button", { name: approveBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: revokeBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: clearBtn })).toBeTruthy();

      expect(screen.queryByText("Pending requests (1)")).toBeNull();
      expect(screen.queryByText("Approved users (1)")).toBeNull();
      expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Revoke" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Clear pending" })).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "暂无待审核申请",
      "暂无已授权用户",
    ],
    [
      "zh-hant",
      "暫無待稽核申請",
      "暫無已授權使用者",
    ],
  ])(
    "renders empty states in %s",
    async (locale, noPending, noApproved) => {
      localStorage.setItem("hermes-locale", locale);
      getPairing.mockResolvedValue({
        pending: [],
        approved: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(noPending)).toBeTruthy();
      expect(screen.getByText(noApproved)).toBeTruthy();

      expect(screen.queryByText("No pending pairing requests")).toBeNull();
      expect(screen.queryByText("No approved users")).toBeNull();
    },
  );
});
