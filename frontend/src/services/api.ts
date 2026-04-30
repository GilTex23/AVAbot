import { getTelegramInitData } from "../lib/telegram";
import type { QuietHoursSettings, ScheduleDay, SubscriptionItem, UpdateItem, UserProfile } from "../lib/types";

const devTgId = import.meta.env.VITE_DEV_TG_ID as string | undefined;

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
      ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(await response.text());
  }

  return response.json() as Promise<T>;
}

export function getProfile(): Promise<UserProfile> {
  return fetchJson<UserProfile>("/api/miniapp/me");
}

export function getUpdates(voiceover: string): Promise<{ voiceover: string; items: UpdateItem[] }> {
  return fetchJson(`/api/miniapp/updates?voiceover=${encodeURIComponent(voiceover)}`);
}

export function getSubscriptions(): Promise<{ items: SubscriptionItem[] }> {
  return fetchJson("/api/miniapp/subscriptions");
}

export function addSubscription(item: UpdateItem) {
  return fetchJson<{ ok: boolean; created: boolean }>("/api/miniapp/subscriptions", {
    method: "POST",
    body: JSON.stringify({
      title: item.title,
      link: item.link,
      episode: item.episode,
      voiceover: item.studio,
    }),
  });
}

export function deleteSubscription(id: number) {
  return fetchJson(`/api/miniapp/subscriptions/${id}`, { method: "DELETE" });
}

export function getSchedule(): Promise<{ days: ScheduleDay[] }> {
  return fetchJson("/api/miniapp/schedule");
}

export function saveVoiceover(voiceover: string) {
  return fetchJson<{ favorite_voiceover: string }>("/api/miniapp/settings/voiceover", {
    method: "PUT",
    body: JSON.stringify({ voiceover }),
  });
}

export function saveQuietHours(settings: QuietHoursSettings) {
  return fetchJson<{
    quiet_hours_enabled: boolean;
    quiet_hours_start: string;
    quiet_hours_end: string;
    quiet_timezone: string;
  }>("/api/miniapp/settings/quiet-hours", {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}
