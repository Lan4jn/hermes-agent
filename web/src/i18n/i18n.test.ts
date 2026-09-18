import { describe, expect, it } from "vitest";
import { en } from "./en";
import { zh } from "./zh";

function getAllKeys(obj: object, prefix = ""): string[] {
  let keys: string[] = [];
  const record = obj as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;
    const value = record[key];
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      keys = keys.concat(getAllKeys(value as object, fullPath));
    } else {
      keys.push(fullPath);
    }
  }
  return keys.sort();
}

function getValue(obj: object, path: string): unknown {
  const parts = path.split(".");
  let curr: unknown = obj;
  for (const p of parts) {
    if (curr === undefined || curr === null || typeof curr !== "object") return undefined;
    curr = (curr as Record<string, unknown>)[p];
  }
  return curr;
}

function extractPlaceholders(str: string): string[] {
  const matches = str.match(/\{([a-zA-Z0-9_]+)\}/g) || [];
  return Array.from(new Set(matches.filter((m) => m !== "{s}"))).sort();
}

describe("i18n dictionary completeness", () => {
  const enKeys = getAllKeys(en);
  const zhKeys = getAllKeys(zh);

  it("has identical key sets between en and zh", () => {
    const missingInZh = enKeys.filter((k) => !zhKeys.includes(k));
    const extraInZh = zhKeys.filter((k) => !enKeys.includes(k));

    expect(missingInZh, `Keys missing in zh: ${missingInZh.join(", ")}`).toEqual([]);
    expect(extraInZh, `Unexpected extra keys in zh: ${extraInZh.join(", ")}`).toEqual([]);
  });

  it("contains non-empty strings or functions for all keys", () => {
    for (const key of enKeys) {
      const enVal = getValue(en, key);
      const zhVal = getValue(zh, key);

      expect(zhVal, `Missing value in zh for key: ${key}`).toBeDefined();
      if (typeof enVal === "string") {
        expect(typeof zhVal, `Type mismatch for key: ${key}`).toBe("string");
        expect((zhVal as string).trim(), `Empty string for key: ${key}`).not.toBe("");
      } else if (typeof enVal === "function") {
        expect(typeof zhVal, `Type mismatch for key: ${key}`).toBe("function");
      }
    }
  });

  it("preserves placeholders between en and zh strings", () => {
    for (const key of enKeys) {
      const enVal = getValue(en, key);
      const zhVal = getValue(zh, key);

      if (typeof enVal === "string" && typeof zhVal === "string") {
        const enPlaceholders = extractPlaceholders(enVal);
        const zhPlaceholders = extractPlaceholders(zhVal);
        expect(
          zhPlaceholders,
          `Placeholder mismatch in key "${key}": EN has ${JSON.stringify(enPlaceholders)}, ZH has ${JSON.stringify(zhPlaceholders)}`
        ).toEqual(enPlaceholders);
      }
    }
  });

  it("enforces standard Chinese terminology", () => {
    // Terminology rules:
    // Gateway -> 网关, Session -> 会话, Profile -> 配置档案, Provider -> 服务商,
    // Skill -> 技能, Toolset -> 工具集, Cron -> 定时任务, Model -> 模型
    expect(zh.app.nav.sessions).toContain("会话");
    expect(zh.app.nav.skills).toContain("技能");
    expect(zh.app.nav.cron).toContain("定时任务");
    expect(zh.app.nav.models).toContain("模型");
    expect(zh.app.nav.profiles).toBe("配置档案");
    expect(zh.common.gateway).toContain("网关");
  });
});
