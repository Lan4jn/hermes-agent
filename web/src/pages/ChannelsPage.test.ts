import { describe, expect, it } from "vitest";
import type { MessagingPlatformEnvVar } from "@/lib/api";
import { channelsEn } from "@/i18n/pagesEn";
import { channelsZh } from "@/i18n/pagesZh";
import { localizeMessagingField } from "@/lib/messaging-field-localization";

const groupField: MessagingPlatformEnvVar = {
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
};

describe("QQ messaging field localization", () => {
  it("uses the selected locale for QQ field metadata", () => {
    expect(localizeMessagingField("qqbot", groupField, channelsZh)).toMatchObject({
      prompt: "允许群消息的 QQ 群 OpenID",
      description: expect.stringContaining("仍需 @机器人"),
    });
    expect(localizeMessagingField("qqbot", groupField, channelsEn)).toMatchObject({
      prompt: "Allowed QQ group OpenIDs",
    });
  });

  it("leaves non-QQ metadata unchanged", () => {
    expect(localizeMessagingField("telegram", groupField, channelsZh)).toBe(groupField);
  });
});
