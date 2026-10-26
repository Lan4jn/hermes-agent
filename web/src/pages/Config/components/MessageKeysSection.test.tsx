import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { fireEvent } from "@testing-library/react";
import type { ReactNode } from "react";

import { I18nProvider } from "@/i18n";

const apiMocks = vi.hoisted(() => ({
  getMessageKeys: vi.fn(),
  getMessagePolicy: vi.fn(),
  updateMessagePolicy: vi.fn(),
  createMessageKey: vi.fn(),
  revokeMessageKey: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: {
    getMessageKeys: apiMocks.getMessageKeys,
    getMessagePolicy: apiMocks.getMessagePolicy,
    updateMessagePolicy: apiMocks.updateMessagePolicy,
    createMessageKey: apiMocks.createMessageKey,
    revokeMessageKey: apiMocks.revokeMessageKey,
  },
}));

vi.mock("@/lib/clipboard", () => ({
  copyTextToClipboard: vi.fn(async () => true),
}));

import { MessageKeysSection } from "./MessageKeysSection";

let container: HTMLDivElement;
let root: Root;

async function render(ui: ReactNode) {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
  await act(async () => root.render(<I18nProvider>{ui}</I18nProvider>));
}

describe("MessageKeysSection", () => {
  beforeEach(() => {
    Object.defineProperty(globalThis, "IS_REACT_ACT_ENVIRONMENT", {
      value: true,
      configurable: true,
      writable: true,
    });
    vi.clearAllMocks();
    apiMocks.getMessageKeys.mockResolvedValue([
      { id: "key-12345678", name: "test-node", created_at: "2026-09-25T12:00:00Z" },
    ]);
    apiMocks.getMessagePolicy.mockResolvedValue({ require_chat_key: false });
    apiMocks.updateMessagePolicy.mockImplementation(async (val: boolean) => ({
      require_chat_key: val,
    }));
    apiMocks.createMessageKey.mockImplementation(async (name: string) => ({
      id: "key-new",
      name,
      created_at: "2026-09-25T13:00:00Z",
      key: "hmmsg_one_time_secret_123",
    }));
    apiMocks.revokeMessageKey.mockResolvedValue({ ok: true, removed: true });
  });

  afterEach(async () => {
    await act(async () => root?.unmount());
    container?.remove();
  });

  it("renders key list and policy status", async () => {
    await render(<MessageKeysSection />);
    expect(container.textContent).toContain("test-node");
    expect(container.textContent).toContain("Optional (Unprotected)");
  });

  it("toggles require_chat_key policy", async () => {
    await render(<MessageKeysSection />);
    const toggleBtn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes("Optional (Unprotected)"),
    );
    expect(toggleBtn).toBeDefined();

    await act(async () => {
      toggleBtn?.click();
    });

    expect(apiMocks.updateMessagePolicy).toHaveBeenCalledWith(true);
    expect(container.textContent).toContain("Required (Protected)");
  });

  it("creates a key and shows one-time secret", async () => {
    await render(<MessageKeysSection />);
    const input = container.querySelector("input[placeholder*='Key label']") as HTMLInputElement;
    expect(input).toBeDefined();

    await act(async () => {
      fireEvent.change(input, { target: { value: "new-worker" } });
    });

    const createForm = container.querySelector("form")!;
    await act(async () => {
      fireEvent.submit(createForm);
    });

    expect(apiMocks.createMessageKey).toHaveBeenCalledWith("new-worker");
    expect(container.textContent).toContain("New Key Created — Copy Now");
    const secretInput = container.querySelector("input[readonly]") as HTMLInputElement;
    expect(secretInput).toBeDefined();
    expect(secretInput.value).toBe("hmmsg_one_time_secret_123");
  });

  it("revokes a key upon confirmation", async () => {
    await render(<MessageKeysSection />);
    const revokeBtn = container.querySelector("button[aria-label='Revoke test-node']") as HTMLButtonElement;
    expect(revokeBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(revokeBtn);
    });

    const confirmBtn = Array.from(document.body.querySelectorAll("button")).find((b) =>
      b.textContent?.trim().includes("Revoke"),
    );
    expect(confirmBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(confirmBtn!);
    });

    expect(apiMocks.revokeMessageKey).toHaveBeenCalledWith("key-12345678");
    expect(container.textContent).not.toContain("test-node");
  });
});
