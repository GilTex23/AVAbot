export type Voiceover = "AniLiberty" | "AniDUB" | "Dream Cast" | "SHIZA Project" | "AnimeVost" | "Все" | string;

export type UserProfile = {
  id: number;
  username?: string | null;
  photo_url?: string | null;
  favorite_voiceover?: string | null;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  quiet_timezone: string;
  subscriptions_count: number;
  is_admin?: boolean;
};

export type UpdateItem = {
  title: string;
  episode: string;
  studio: string;
  link: string;
  poster_url?: string;
};

export type NextEpisodeForecast = {
  episode: number;
  expected_at: string;
  earliest_at: string;
  latest_at: string;
  /** Выход оригинала серии; air_estimated — если посчитан по соседней серии, а не взят из расписания */
  air_at?: string | null;
  air_estimated: boolean;
  /** title — по истории этой озвучки на тайтле, studio — по другим тайтлам студии, cadence — по интервалу между сериями, airing — выход оригинала (для «Все») */
  basis: "title" | "studio" | "cadence" | "airing";
  lag_hours?: number | null;
  samples: number;
  overdue: boolean;
};

export type SubscriptionItem = {
  id: number;
  title: string;
  link: string;
  poster_url?: string | null;
  voiceover: string;
  last_episode?: string | null;
  total_episodes?: number | null;
  next_episode?: NextEpisodeForecast | null;
};

/** Серия из «Моих серий на неделе»: подписка + прогноз конкретной серии */
export type WeekItem = SubscriptionItem & {
  forecast: NextEpisodeForecast;
};

export type ScheduleItem = {
  title: string;
  link: string;
  time: string;
  poster_url?: string;
};

export type AnimeDetails = {
  type?: string | null;
  status?: string | null;
  total_episodes?: number | null;
  voiceovers: string[];
};

export type ScheduleDay = {
  date_str: string;
  items: ScheduleItem[];
};

export type TabId = "updates" | "subscriptions" | "schedule" | "settings";

export type QuietHoursSettings = {
  enabled: boolean;
  start: string;
  end: string;
  timezone: string;
};

export type ScraperKeyStatus = "active" | "low" | "exhausted" | "invalid";

export type ScraperKey = {
  id: number;
  name: string;
  email?: string | null;
  masked_key: string;
  decrypt_error: boolean;
  enabled: boolean;
  status: ScraperKeyStatus;
  request_count?: number | null;
  request_limit?: number | null;
  failed_request_count?: number | null;
  remaining?: number | null;
  subscription_date?: string | null;
  last_checked_at?: string | null;
  last_used_at?: string | null;
  last_error?: string | null;
  last_error_at?: string | null;
  created_at?: string | null;
};

export type ScraperUsageDay = {
  day: string;
  success: number;
  failed: number;
};

export type ScraperKeysOverview = {
  keys: ScraperKey[];
  usage: ScraperUsageDay[];
  summary: {
    total_keys: number;
    usable_keys: number;
    remaining: number;
    limit: number;
    avg_daily: number | null;
    days_left: number | null;
  };
  subscriptions_check_running: boolean;
  parser_health: ParserHealth;
};

export type ParserHealth = {
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  updates_count: number;
  schedule_count: number;
  timed_schedule_count: number;
  timezone?: string | null;
  problems: string[];
  consecutive_failures: number;
  failure_threshold: number;
};

export type NewScraperKey = {
  name: string;
  email: string;
  key: string;
};

export type ScraperKeyPatch = Partial<{ name: string; email: string; enabled: boolean }>;
