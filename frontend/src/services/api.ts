import { getTelegramInitData } from "../lib/telegram";
import type { ScheduleDay, SubscriptionItem, UpdateItem, UserProfile } from "../lib/types";

const devTgId = import.meta.env.VITE_DEV_TG_ID as string | undefined;

const demoPosters = [
  "https://img.cdngos.com/v/250x350/anime/69/69b0592904754519432210",
  "https://img.cdngos.com/v/250x350/anime/69/69ac809616440394945957",
  "https://img.cdngos.com/v/250x350/anime/69/69bdd67ff0004316149754",
  "https://img.cdngos.com/v/250x350/anime/69/69931f2ec8324654853656",
];

export const demoUpdates: UpdateItem[] = [
  {
    title: "Ателье колдовских колпаков",
    episode: "Серия 5",
    studio: "AniLiberty",
    link: "https://animego.me/anime/atel-ye-koldovskikh-kolpakov-3280",
    poster_url: demoPosters[0],
  },
  {
    title: "Re: Жизнь в альтернативном мире с нуля 4",
    episode: "Серия 5",
    studio: "Dream Cast",
    link: "https://animego.me/anime/re-zhizn-v-al-ternativnom-mire-s-nulya-4-3279",
    poster_url: demoPosters[1],
  },
  {
    title: "Доктор Стоун: Научное будущее. Часть 3",
    episode: "Серия 5",
    studio: "AnimeVost",
    link: "https://animego.me/anime/doktor-stoun-nauchnoye-budushcheye-chast-3-3311",
    poster_url: demoPosters[2],
  },
  {
    title: "Дорохедоро 2",
    episode: "Серия 4",
    studio: "SHIZA Project",
    link: "https://animego.me/anime/dorokhedoro-2-3231",
    poster_url: demoPosters[3],
  },
];

const demoSchedule: ScheduleDay[] = [
  {
    date_str: "Сегодня",
    items: demoUpdates.map((item, index) => ({
      title: item.title,
      link: item.link,
      poster_url: item.poster_url,
      time: ["16:00", "17:30", "18:00", "19:30"][index],
    })),
  },
];

const demoSubscriptions: SubscriptionItem[] = [
  {
    id: 1,
    title: "Ателье колдовских колпаков",
    link: demoUpdates[0].link,
    voiceover: "AniLiberty",
    last_episode: "Серия 4",
    total_episodes: 13,
  },
  {
    id: 2,
    title: "Re: Жизнь в альтернативном мире с нуля 4",
    link: demoUpdates[1].link,
    voiceover: "Dream Cast",
    last_episode: "Серия 4",
    total_episodes: 19,
  },
];

function authQuery() {
  return devTgId ? `tg_id=${encodeURIComponent(devTgId)}` : "";
}

async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const initData = getTelegramInitData();
  const separator = path.includes("?") ? "&" : "?";
  const url = devTgId ? `${path}${separator}${authQuery()}` : path;

  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(initData ? { "x-telegram-init-data": initData } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}

export async function getProfile(): Promise<UserProfile> {
  try {
    return await fetchJson<UserProfile>("/api/miniapp/me");
  } catch {
    return {
      id: Number(devTgId || 0),
      username: "giltix",
      favorite_voiceover: "AniLiberty",
      subscriptions_count: demoSubscriptions.length,
    };
  }
}

export async function getUpdates(voiceover: string): Promise<{ voiceover: string; items: UpdateItem[] }> {
  try {
    return await fetchJson(`/api/miniapp/updates?voiceover=${encodeURIComponent(voiceover)}`);
  } catch {
    const items = voiceover === "Все" ? demoUpdates : demoUpdates.filter((item) => item.studio.includes(voiceover));
    return { voiceover, items: items.length ? items : demoUpdates };
  }
}

export async function getSubscriptions(): Promise<{ items: SubscriptionItem[] }> {
  try {
    return await fetchJson("/api/miniapp/subscriptions");
  } catch {
    return { items: demoSubscriptions };
  }
}

export async function deleteSubscription(id: number) {
  try {
    await fetchJson(`/api/miniapp/subscriptions/${id}`, { method: "DELETE" });
  } catch {
    return;
  }
}

export async function getSchedule(): Promise<{ days: ScheduleDay[] }> {
  try {
    return await fetchJson("/api/miniapp/schedule");
  } catch {
    return { days: demoSchedule };
  }
}

export async function saveVoiceover(voiceover: string) {
  try {
    return await fetchJson<{ favorite_voiceover: string }>("/api/miniapp/settings/voiceover", {
      method: "PUT",
      body: JSON.stringify({ voiceover }),
    });
  } catch {
    return { favorite_voiceover: voiceover };
  }
}
