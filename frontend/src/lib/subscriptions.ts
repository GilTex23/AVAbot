import type { SubscriptionItem } from "./types";

export type SubscriptionIndex = {
  byAnime: Map<string, SubscriptionItem[]>;
  byAnimeVoiceover: Set<string>;
};

export function normalizeAnimeLink(link: string) {
  return link.split("#")[0].replace(/\/+$/, "");
}

export function subscriptionKey(link: string, voiceover: string) {
  return `${normalizeAnimeLink(link)}::${voiceover.trim().toLowerCase()}`;
}

export function buildSubscriptionIndex(subscriptions: SubscriptionItem[]): SubscriptionIndex {
  const byAnime = new Map<string, SubscriptionItem[]>();
  const byAnimeVoiceover = new Set<string>();

  for (const subscription of subscriptions) {
    const animeKey = normalizeAnimeLink(subscription.link);
    const animeSubscriptions = byAnime.get(animeKey) || [];
    animeSubscriptions.push(subscription);
    byAnime.set(animeKey, animeSubscriptions);
    byAnimeVoiceover.add(subscriptionKey(subscription.link, subscription.voiceover));
  }

  return { byAnime, byAnimeVoiceover };
}
