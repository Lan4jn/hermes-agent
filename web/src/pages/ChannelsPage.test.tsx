import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { type ReactNode, useMemo, useState } from "react";

import { I18nProvider } from "@/i18n";
import { PageHeaderContext } from "@/contexts/page-header-context";

const { getMessagingPlatforms, testMessagingPlatform, restartGateway } = vi.hoisted(() => ({
  getMessagingPlatforms: vi.fn(),
  testMessagingPlatform: vi.fn(),
  restartGateway: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getMessagingPlatforms,
    testMessagingPlatform,
    restartGateway,
    updateMessagingPlatform: vi.fn(),
    getActionStatus: vi.fn(),
    startTelegramOnboarding: vi.fn(),
    cancelTelegramOnboarding: vi.fn(),
    getTelegramOnboardingStatus: vi.fn(),
    applyTelegramOnboarding: vi.fn(),
    startWhatsAppOnboarding: vi.fn(),
    cancelWhatsAppOnboarding: vi.fn(),
    getWhatsAppOnboardingStatus: vi.fn(),
    applyWhatsAppOnboarding: vi.fn(),
  },
}));

import ChannelsPage from "./ChannelsPage";

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
        <ChannelsPage />
      </PageHeaderContext.Provider>
    </I18nProvider>
  );
}

beforeEach(() => {
  cleanup();
  localStorage.clear();
  getMessagingPlatforms.mockReset();
  testMessagingPlatform.mockReset();
  restartGateway.mockReset();
});

describe("ChannelsPage localization", () => {
  it.each([
    [
      "zh",
      "已配置 1 / 2 个渠道",
      "启用 Telegram",
      "测试",
      "配置",
      "快速设置",
      "推荐",
      "使用你自己的 Bot",
      "手动设置",
      "重启网关",
    ],
    [
      "zh-hant",
      "已配置 1 / 2 個渠道",
      "啟用 Telegram",
      "測試",
      "配置",
      "快速設定",
      "推薦",
      "使用你自己的 Bot",
      "手動設定",
      "重啟閘道器",
    ],
  ])(
    "renders normal channels state in %s without English fallbacks",
    async (
      locale,
      summarySubstr,
      telegramAriaLabel,
      testBtn,
      configBtn,
      quickSetup,
      recommendedBadge,
      useOwnBot,
      manualSetup,
      restartBtn,
    ) => {
      localStorage.setItem("hermes-locale", locale);
      getMessagingPlatforms.mockResolvedValue({
        platforms: [
          {
            id: "telegram",
            name: "Telegram",
            description: "Telegram Bot platform",
            enabled: true,
            configured: true,
            state: "connected",
            gateway_running: true,
            env_vars: [],
          },
          {
            id: "feishu",
            name: "Feishu",
            description: "Feishu integration",
            enabled: false,
            configured: false,
            state: "not_configured",
            gateway_running: true,
            env_vars: [],
          },
        ],
        env_path: "~/.hermes/.env",
        gateway_start_command: "hermes gateway start",
      });

      render(<TestWrapper />);

      expect(
        await screen.findByText((_, element) =>
          element?.tagName === "P" && Boolean(element.textContent?.includes(summarySubstr)),
        ),
      ).toBeTruthy();

      expect(screen.getByRole("switch", { name: telegramAriaLabel })).toBeTruthy();
      expect(screen.getAllByRole("button", { name: testBtn }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getByRole("button", { name: configBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: restartBtn })).toBeTruthy();

      // Telegram onboarding / setup section
      expect(screen.getByText(quickSetup)).toBeTruthy();
      expect(screen.getByText(recommendedBadge)).toBeTruthy();
      expect(screen.getByText(useOwnBot)).toBeTruthy();
      expect(screen.getByRole("button", { name: manualSetup })).toBeTruthy();

      // Old English text must not appear
      expect(screen.queryByText(/1 of 2 channels configured/i)).toBeNull();
      expect(screen.queryByRole("switch", { name: "Enable Telegram" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Test" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Restart gateway" })).toBeNull();
      expect(screen.queryByText("Quick setup")).toBeNull();
      expect(screen.queryByText("recommended")).toBeNull();
      expect(screen.queryByText("Use your own bot")).toBeNull();
      expect(screen.queryByRole("button", { name: "Manual setup" })).toBeNull();
    },
  );

  it.each([
    ["zh", "网关未运行。在此配置渠道后，请运行命令或点击上方重启按钮启动网关。"],
    ["zh-hant", "閘道器未運行。在此配置渠道後，請運行命令或點擊上方重啟按鈕啟動閘道器。"],
  ])("renders gateway stopped state in %s", async (locale, stoppedMsg) => {
    localStorage.setItem("hermes-locale", locale);
    getMessagingPlatforms.mockResolvedValue({
      platforms: [
        {
          id: "telegram",
          name: "Telegram",
          description: "Telegram Bot",
          enabled: false,
          configured: false,
          state: "not_configured",
          gateway_running: false,
          env_vars: [],
        },
      ],
      env_path: "~/.hermes/.env",
      gateway_start_command: "hermes gateway start",
    });

    render(<TestWrapper />);

    expect(await screen.findByText(stoppedMsg)).toBeTruthy();
    expect(screen.queryByText(/The gateway is not running/i)).toBeNull();
  });

  it.each([
    ["zh", "渠道管理失败：gateway timeout"],
    ["zh-hant", "渠道管理失敗：gateway timeout"],
  ])("renders error state on load failure in %s", async (locale, errorMsg) => {
    localStorage.setItem("hermes-locale", locale);
    getMessagingPlatforms.mockRejectedValue(new Error("gateway timeout"));

    render(<TestWrapper />);

    expect(await screen.findByText(errorMsg)).toBeTruthy();
    expect(screen.queryByText(/Could not load channels/i)).toBeNull();
  });

  it.each([
    [
      "zh",
      "配置 QQ 机器人",
      "允许群消息的 QQ 群 OpenID",
      "保存并启用",
      "取消",
    ],
    [
      "zh-hant",
      "配置 QQ 機器人",
      "允許群訊息的 QQ 群 OpenID",
      "儲存並啟用",
      "取消",
    ],
  ])(
    "renders QQ channel configuration modal with localized fields in %s",
    async (locale, modalTitle, groupFieldPrompt, saveBtn, cancelBtn) => {
      localStorage.setItem("hermes-locale", locale);
      getMessagingPlatforms.mockResolvedValue({
        platforms: [
          {
            id: "qqbot",
            name: locale === "zh" ? "QQ 机器人" : "QQ 機器人",
            description: "QQ Bot platform",
            enabled: false,
            configured: false,
            state: "not_configured",
            gateway_running: true,
            env_vars: [
              {
                key: "QQ_GROUP_ALLOWED_USERS",
                required: false,
                is_set: false,
                redacted_value: null,
                description: "backend description",
                prompt: "backend prompt",
                help: "",
                url: null,
                is_password: false,
                advanced: false,
              },
            ],
          },
        ],
        env_path: "~/.hermes/.env",
        gateway_start_command: "hermes gateway start",
      });

      render(<TestWrapper />);

      const configBtn = await screen.findByRole("button", { name: "配置" });
      fireEvent.click(configBtn);

      expect(await screen.findByText(modalTitle)).toBeTruthy();
      expect(screen.getByText(groupFieldPrompt)).toBeTruthy();
      expect(screen.getByRole("button", { name: saveBtn })).toBeTruthy();
      expect(screen.getByRole("button", { name: cancelBtn })).toBeTruthy();
    },
  );
});
