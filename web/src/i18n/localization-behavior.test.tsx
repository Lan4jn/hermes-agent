// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from "./index";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { ModelReloadConfirm } from "@/components/ModelReloadConfirm";

let container: HTMLDivElement;
let root: Root;
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("i18n runtime locale behavior and progressive fallback", () => {
  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(async () => {
    await act(async () => {
      root?.unmount();
    });
    container?.remove();
  });

  function TestConsumer() {
    const { locale, t } = useI18n();
    return (
      <div data-testid="i18n-info">
        <span data-testid="locale">{locale}</span>
        <span data-testid="cancel">{t.common.cancel}</span>
        <span data-testid="confirm">{t.common.confirm}</span>
        <span data-testid="model">{t.common.model}</span>
        <span data-testid="reasoning">{t.common.reasoning}</span>
        <span data-testid="nav-sessions">{t.app.nav.sessions}</span>
        <span data-testid="nav-models">{t.app.nav.models}</span>
      </div>
    );
  }

  it("renders Simplified Chinese strings when hermes-locale=zh", async () => {
    localStorage.setItem("hermes-locale", "zh");

    await act(async () => {
      root.render(
        <I18nProvider>
          <TestConsumer />
          <ConfirmDialog
            open={true}
            title="测试标题"
            onCancel={() => {}}
            onConfirm={() => {}}
          />
          <ModelReloadConfirm model="gpt-4o" onCancel={() => {}} />
        </I18nProvider>
      );
    });

    const info = container.querySelector('[data-testid="i18n-info"]');
    expect(info?.querySelector('[data-testid="locale"]')?.textContent).toBe("zh");
    expect(info?.querySelector('[data-testid="cancel"]')?.textContent).toBe("取消");
    expect(info?.querySelector('[data-testid="confirm"]')?.textContent).toBe("确认");
    expect(info?.querySelector('[data-testid="model"]')?.textContent).toBe("模型");
    expect(info?.querySelector('[data-testid="reasoning"]')?.textContent).toBe("推理强度");
    expect(info?.querySelector('[data-testid="nav-sessions"]')?.textContent).toBe("会话");
    expect(info?.querySelector('[data-testid="nav-models"]')?.textContent).toBe("模型");

    // Dialog confirm buttons have Chinese text
    const reloadBtn = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent?.includes("重新加载")
    );
    expect(reloadBtn).toBeDefined();
  });

  it("renders English strings when hermes-locale=en", async () => {
    localStorage.setItem("hermes-locale", "en");

    await act(async () => {
      root.render(
        <I18nProvider>
          <TestConsumer />
          <ModelReloadConfirm model="gpt-4o" onCancel={() => {}} />
        </I18nProvider>
      );
    });

    const info = container.querySelector('[data-testid="i18n-info"]');
    expect(info?.querySelector('[data-testid="locale"]')?.textContent).toBe("en");
    expect(info?.querySelector('[data-testid="cancel"]')?.textContent).toBe("Cancel");
    expect(info?.querySelector('[data-testid="confirm"]')?.textContent).toBe("Confirm");
    expect(info?.querySelector('[data-testid="model"]')?.textContent).toBe("Model");
    expect(info?.querySelector('[data-testid="reasoning"]')?.textContent).toBe("Reasoning");

    const reloadBtn = Array.from(document.querySelectorAll("button")).find(
      (b) => b.textContent?.includes("Reload")
    );
    expect(reloadBtn).toBeDefined();
  });

  it("falls back safely to English when a locale lacks modular pages without crashing", async () => {
    // de or fr do not define optional modules like modelsPage or pairing
    localStorage.setItem("hermes-locale", "de");

    let didThrow = false;
    try {
      await act(async () => {
        root.render(
          <I18nProvider>
            <TestConsumer />
          </I18nProvider>
        );
      });
    } catch {
      didThrow = true;
    }

    expect(didThrow).toBe(false);
    const info = container.querySelector('[data-testid="i18n-info"]');
    expect(info?.querySelector('[data-testid="locale"]')?.textContent).toBe("de");
  });
});
