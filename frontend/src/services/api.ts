import { getTelegramInitData } from "../lib/telegram";
import type {
  AdminStats,
  AnimeDetails,
  NewScraperKey,
  QuietHoursSettings,
  ScheduleDay,
  ScheduleItem,
  ScraperKeyPatch,
  ScraperKeysOverview,
  ShikimoriOverview,
  SubscriptionItem,
  UpdateItem,
  UpdatesResponse,
  UserProfile,
  VoiceoverCatalogItem,
  WeekItem,
} from "../lib/types";

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

/** Без voiceover — по любимым озвучкам; ALL_VOICEOVERS — все серии */
export function getUpdates(voiceover?: string | null): Promise<UpdatesResponse> {
  return fetchJson(voiceover ? `/api/miniapp/updates?voiceover=${encodeURIComponent(voiceover)}` : "/api/miniapp/updates");
}

export function getVoiceovers(): Promise<{ items: VoiceoverCatalogItem[]; popular_days: number }> {
  return fetchJson("/api/miniapp/voiceovers");
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

export function getMyWeek(): Promise<{ items: WeekItem[] }> {
  return fetchJson("/api/miniapp/my-week");
}

/** Текст ошибки для пользователя: причина отказа от бэкенда (400/409) или общий текст */
export function errorText(error: unknown, fallback: string) {
  return error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 401 ? error.message : fallback;
}

export function getSchedule(): Promise<{ days: ScheduleDay[] }> {
  return fetchJson("/api/miniapp/schedule");
}

export function getAnimeDetails(link: string): Promise<AnimeDetails> {
  return fetchJson(`/api/miniapp/anime-details?link=${encodeURIComponent(link)}`);
}

export function saveFavoriteVoiceovers(voiceovers: string[]) {
  return fetchJson<{ favorite_voiceovers: string[] }>("/api/miniapp/settings/voiceovers", {
    method: "PUT",
    body: JSON.stringify({ voiceovers }),
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

export function saveTimeZone(timezone: string) {
  return fetchJson<{ quiet_timezone: string }>("/api/miniapp/settings/timezone", {
    method: "PUT",
    body: JSON.stringify({ timezone }),
  });
}

export function getAdminStats(days: number): Promise<AdminStats> {
  return fetchJson(`/api/miniapp/admin/stats?days=${days}`);
}

export function getAdminKeys(): Promise<ScraperKeysOverview> {
  return fetchJson("/api/miniapp/admin/keys");
}

export function addAdminKey(key: NewScraperKey): Promise<ScraperKeysOverview> {
  return fetchJson("/api/miniapp/admin/keys", { method: "POST", body: JSON.stringify(key) });
}

export function updateAdminKey(id: number, patch: ScraperKeyPatch): Promise<ScraperKeysOverview> {
  return fetchJson(`/api/miniapp/admin/keys/${id}`, { method: "PATCH", body: JSON.stringify(patch) });
}

export function deleteAdminKey(id: number): Promise<ScraperKeysOverview> {
  return fetchJson(`/api/miniapp/admin/keys/${id}`, { method: "DELETE" });
}

export function refreshAdminKeys(id?: number): Promise<ScraperKeysOverview> {
  return fetchJson(id ? `/api/miniapp/admin/keys/${id}/refresh` : "/api/miniapp/admin/keys/refresh", { method: "POST" });
}

export function getAdminShikimori(): Promise<ShikimoriOverview> {
  return fetchJson("/api/miniapp/admin/shikimori");
}

export function updateShikimoriMatch(animeId: number, payload: { shikimori: string | number } | { absent: true } | { recheck: true }): Promise<ShikimoriOverview> {
  return fetchJson(`/api/miniapp/admin/shikimori/${animeId}`, { method: "PUT", body: JSON.stringify(payload) });
}

export function runShikimoriSync(): Promise<{ started: boolean }> {
  return fetchJson("/api/miniapp/admin/shikimori/sync", { method: "POST" });
}

export function runSubscriptionsCheck(): Promise<{ started: boolean }> {
  return fetchJson("/api/miniapp/admin/subscriptions/check", { method: "POST" });
}
