import { openTelegramLink } from "./telegram";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function openAnime(link: string) {
  openTelegramLink(link);
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
