import { useMemo, useState } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getWebhooks, getDeliveryTargets } = vi.hoisted(() => ({
  getWebhooks: vi.fn(),
  getDeliveryTargets: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getWebhooks,
    getDeliveryTargets,
    createWebhook: vi.fn(),
    deleteWebhook: vi.fn(),
    toggleWebhook: vi.fn(),
    enableWebhookReceiver: vi.fn(),
    restartGateway: vi.fn(),
    getActionStatus: vi.fn(),
  },
}));

import WebhooksPage from "./WebhooksPage";

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
          <WebhooksPage />
        </PageHeaderContext.Provider>
      </I18nProvider>
    </MemoryRouter>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getDeliveryTargets.mockResolvedValue([]);
});

describe("WebhooksPage localization", () => {
  it.each([
    [
      "zh",
      "订阅列表 (1)",
      "新建 Webhook",
      "删除",
    ],
    [
      "zh-hant",
      "訂閱列表 (1)",
      "新建 Webhook",
      "刪除",
    ],
  ])(
    "renders subscriptions and actions in %s without English fallback",
    async (locale, subHeading, newWebhookBtn, deleteBtnAria) => {
      localStorage.setItem("hermes-locale", locale);
      getWebhooks.mockResolvedValue({
        enabled: true,
        subscriptions: [
          {
            name: "github-pr",
            description: "GitHub PR events",
            path: "/hook/github-pr",
            events: ["pull_request"],
            enabled: true,
            deliver: "log",
          },
        ],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(subHeading)).toBeTruthy();
      expect(screen.getByRole("button", { name: newWebhookBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: deleteBtnAria })).toBeTruthy();

      expect(screen.queryByText("Subscriptions (1)")).toBeNull();
      expect(screen.queryByRole("button", { name: "New webhook" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "尚未配置任何 Webhook。",
    ],
    [
      "zh-hant",
      "尚未配置任何 Webhook。",
    ],
  ])(
    "renders empty state in %s",
    async (locale, noWebhooksText) => {
      localStorage.setItem("hermes-locale", locale);
      getWebhooks.mockResolvedValue({
        enabled: true,
        subscriptions: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(noWebhooksText)).toBeTruthy();
      expect(
        screen.queryByText("No webhooks configured. Create one above."),
      ).toBeNull();
    },
  );

  it.each([
    [
      "zh",
      "Webhook 接收服务已禁用",
    ],
    [
      "zh-hant",
      "Webhook 接收服務已禁用",
    ],
  ])(
    "renders disabled receiver notice in %s",
    async (locale, disabledNotice) => {
      localStorage.setItem("hermes-locale", locale);
      getWebhooks.mockResolvedValue({
        enabled: false,
        subscriptions: [],
      });

      render(<TestWrapper />);

      expect(await screen.findByText(disabledNotice)).toBeTruthy();
      expect(screen.queryByText("Webhook receiver is disabled")).toBeNull();
    },
  );
});
