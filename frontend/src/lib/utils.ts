import { botUrl } from "./config";
import { openTelegramChatLink, openTelegramLink } from "./telegram";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function openAnime(link: string) {
  openTelegramLink(link);
}

/** Ссылка на тайтл в боте: t.me/бот?start=a3484 (id из конца адреса AnimeGO); null — если поделиться нельзя */
export function titleDeepLink(link: string) {
  const id = link.split(/[?#]/)[0].match(/-(\d+)\/?$/)?.[1];
  const bot = botUrl.replace(/\/+$/, "");
  if (!id || bot.includes("YOUR_BOT_USERNAME")) {
    return null;
  }
  return `${bot}?start=a${id}`;
}

export function shareTitle(link: string, title: string) {
  const deepLink = titleDeepLink(link);
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
