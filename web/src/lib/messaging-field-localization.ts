import type { MessagingPlatformEnvVar } from "@/lib/api";
import type { ChannelsTranslations } from "@/i18n/pagesTypes";

export function localizeMessagingField(
  platformId: string,
  field: MessagingPlatformEnvVar,
  text: ChannelsTranslations,
): MessagingPlatformEnvVar {
  const translated = platformId === "qqbot" ? text.qqFields[field.key] : undefined;
  return translated ? { ...field, ...translated } : field;
}
