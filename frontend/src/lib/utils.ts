import { botUrl } from "./config";
import { openTelegramChatLink, openTelegramLink } from "./telegram";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function openAnime(link: string) {
  openTelegramLink(link);
}

/**
 * Ссылка на тайтл в боте: t.me/бот?start=a3484 (id из конца адреса AnimeGO) или ?start=y17212 (id на YummyAnime);
 * null — если поделиться нельзя
 */
export function titleDeepLink(link: string, source?: string | null, sourceId?: string | null) {
  const bot = botUrl.replace(/\/+$/, "");
  if (bot.includes("YOUR_BOT_USERNAME")) {
    return null;
  }
  if (source === "yummy") {
    return sourceId && /^\d+$/.test(sourceId) ? `${bot}?start=y${sourceId}` : null;
  }
  const id = link.includes("animego") ? link.split(/[?#]/)[0].match(/-(\d+)\/?$/)?.[1] : undefined;
  return id ? `${bot}?start=a${id}` : null;
}

export function shareTitle(link: string, title: string, source?: string | null, sourceId?: string | null) {
  const deepLink = titleDeepLink(link, source, sourceId);
  if (!deepLink) {
    return;
  }
  const text = `${title} — подпишись на новые серии в озвучке`;
  openTelegramChatLink(`https://t.me/share/url?url=${encodeURIComponent(deepLink)}&text=${encodeURIComponent(text)}`);
}

/** Подписка и фильтр «любая озвучка» — так же называется на бэкенде */
export const ALL_VOICEOVERS = "Все";

/** «AniLiberty, AniDUB и ещё 2» или «Все озвучки» */
export function describeVoiceovers(names: string[], limit = 3) {
  if (!names.length) {
    return "Все озвучки";
  }
  return names.length <= limit ? names.join(", ") : `${names.slice(0, limit).join(", ")} и ещё ${names.length - limit}`;
}
