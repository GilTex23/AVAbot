import { getTelegramInitData } from "../lib/telegram";
import type { AnimeDetails, QuietHoursSettings, ScheduleDay, ScheduleItem, SubscriptionItem, UpdateItem, UserProfile } from "../lib/types";

const devTgId = import.meta.env.VITE_DEV_TG_ID as string | undefined;

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

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
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorMessage(response));
  }

  return response.json() as Promise<T>;
}

async function readErrorMessage(response: Response) {
  const rawText = await response.text();
  if (!rawText) {
    return response.statusText || "Request failed";
  }

  try {
    const parsed: unknown = JSON.parse(rawText);
    if (isErrorPayload(parsed)) {
      return parsed.detail;
    }
  } catch {
    // Non-JSON backend/proxy errors are still useful as plain text.
  }

  return rawText;
}

function isErrorPayload(value: unknown): value is { detail: string } {
  return typeof value === "object" && value !== null && "detail" in value && typeof (value as { detail: unknown }).detail === "string";
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
      poster_url: item.poster_url,
    }),
  });
}

export function addScheduleSubscription(item: ScheduleItem, voiceover: string, totalEpisodes?: number | null) {
  return fetchJson<{ ok: boolean; created: boolean }>("/api/miniapp/subscriptions", {
    method: "POST",
    body: JSON.stringify({
      title: item.title,
      link: item.link,
      episode: "Серия 0",
      voiceover,
      total_episodes: totalEpisodes,
      poster_url: item.poster_url,
    }),
  });
}

export function deleteSubscription(id: number) {
  return fetchJson(`/api/miniapp/subscriptions/${id}`, { method: "DELETE" });
}

export function getSchedule(): Promise<{ days: ScheduleDay[] }> {
  return fetchJson("/api/miniapp/schedule");
}

export function getAnimeDetails(link: string): Promise<AnimeDetails> {
  return fetchJson(`/api/miniapp/anime-details?link=${encodeURIComponent(link)}`);
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
