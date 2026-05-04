import { openTelegramLink } from "./telegram";

export function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

export function openAnime(link: string) {
  openTelegramLink(link);
}

export const voiceovers = ["AniLiberty", "AniDUB", "Dream Cast", "SHIZA Project", "AnimeVost", "Все"];
