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

/** Ряды по дням: значения выровнены по AdminStats.days */
export type DailySeries = Record<string, number[]>;

export type AdminStats = {
  period_days: number;
  days: string[];
  scraper: {
    success_by_source: DailySeries;
    success_by_page: DailySeries;
    by_key: DailySeries;
    failed: number[];
    timeouts: number[];
    failed_by_status: DailySeries;
    cache_hits: number[];
    latency_avg_ms: Array<number | null>;
    credits: Array<{ at: string; remaining: number; limit: number }>;
    key_status_changes: DailySeries;
  };
  bot: {
    users: number;
    subscriptions: number;
    subscribers: number;
    quiet_hours_users: number;
    top_titles: Array<{ title: string; count: number }>;
    voiceovers: Array<{ name: string; count: number }>;
    active_7d: number;
    active_30d: number;
    active_by_source: DailySeries;
    active_total: number[];
    new_users: number[];
    notifications_sent: number[];
    notifications_deferred: number[];
    subscriptions_created: number[];
    subscriptions_deleted: number[];
    subscriptions_completed: number[];
    subscriptions_stale: number[];
  };
  parser: { home_results: DailySeries };
  history: { releases: number; airings: number; titles: number; releases_per_day: number[] };
  database: {
    size_bytes: number;
    tables: Array<{ name: string; rows: number; total_bytes: number; table_bytes: number; index_bytes: number }>;
    connections: number;
    version: string;
    started_at?: string | null;
    retention_days: number;
  };
  server: {
    cpu_percent: number;
    cpu_count: number | null;
    load_average: number[] | null;
    memory_total: number;
    memory_used: number;
    memory_percent: number;
    process_memory: number;
    disk_total: number;
    disk_used: number;
    disk_percent: number;
    logs_bytes: number;
    process_uptime_seconds: number;
    system_uptime_seconds: number;
    python: string;
  };
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
