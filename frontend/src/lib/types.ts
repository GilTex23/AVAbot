export type UserProfile = {
  id: number;
  username?: string | null;
  photo_url?: string | null;
  /** Пустой список — все озвучки */
  favorite_voiceovers: string[];
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
  quiet_timezone: string;
  subscriptions_count: number;
  is_admin?: boolean;
};

export type SourceId = "animego" | "yummy";

/** Оценка тайтла на сайте (из 10) */
export type RatingItem = {
  source: "animego" | "shikimori" | "yummy";
  value: number;
  votes?: number | null;
  url?: string | null;
};

export type UpdateItem = {
  title: string;
  episode: string;
  studio: string;
  link: string;
  poster_url?: string;
  /** Нет — AnimeGO; yummy — лента YummyAnime, source_id — id тайтла там */
  source?: SourceId;
  source_id?: string;
};

export type YummyTitle = {
  id: number;
  title: string;
  url: string;
  poster_url?: string | null;
  kind?: string | null;
  status?: string | null;
  year?: number | null;
  total_episodes?: number | null;
  episodes_aired?: number | null;
  next_episode_at?: string | null;
  /** Собственная оценка YummyAnime */
  rating?: number | null;
  rating_votes?: number | null;
};

export type YummyTitleDetails = YummyTitle & {
  ratings?: RatingItem[];
  voiceovers: Array<{ name: string; last_episode: number; updated_at: string }>;
};

export type AdminUser = {
  id: number;
  username?: string | null;
  photo_url?: string | null;
  registered_at?: string | null;
  /** День последней активности в UTC: «2026-09-14» */
  last_active?: string | null;
  subscriptions: number;
  yummy_subscriptions: number;
  favorite_voiceovers: string[];
  timezone: string;
  quiet_hours: { enabled: boolean; start: string; end: string };
  is_admin: boolean;
};

export type AdminUserDetails = AdminUser & {
  active_days: number;
  activity_days: number;
  activity_sources: string[];
  subscriptions_list: Array<{
    id: number;
    title: string;
    link: string;
    poster_url?: string | null;
    voiceover: string;
    source: SourceId;
    last_episode?: string | null;
    total_episodes?: number | null;
    last_episode_at?: string | null;
  }>;
};

export type ShikimoriTitleStatus = "pending" | "matched" | "manual" | "not_found" | "ambiguous" | "absent" | "error";

export type ShikimoriCandidate = {
  id: number;
  name?: string | null;
  russian?: string | null;
  kind?: string | null;
  year?: number | null;
  episodes?: number | null;
  url?: string | null;
  score?: number | null;
};

export type ShikimoriTitle = {
  id: number;
  title: string;
  url: string;
  poster_url?: string | null;
  subscriptions: number;
  status: ShikimoriTitleStatus;
  checked_at?: string | null;
  error?: string | null;
  /** Данные со страницы AnimeGO, по которым ищется тайтл */
  animego: { english_title?: string | null; kind?: string | null; year?: number | null; episodes?: number | null };
  shikimori?: {
    id: number;
    name: string;
    russian?: string | null;
    kind?: string | null;
    status?: string | null;
    episodes?: number | null;
    episodes_aired?: number | null;
    next_episode_at?: string | null;
    year?: number | null;
    url?: string | null;
    synced_at?: string | null;
  } | null;
  candidates: ShikimoriCandidate[];
};

export type ShikimoriOverview = {
  enabled: boolean;
  running: boolean;
  summary: Record<ShikimoriTitleStatus, number>;
  titles: ShikimoriTitle[];
};

export type UpdatesResponse = {
  source: SourceId;
  /** favorites — по любимым озвучкам (нет любимых — все), all — все, voiceover — одна озвучка */
  filter: "favorites" | "all" | "voiceover";
  voiceover?: string | null;
  favorites: string[];
  items: UpdateItem[];
  /** Озвучки, которые сейчас есть в ленте, самые частые первыми */
  studios: Array<{ name: string; count: number }>;
};

export type VoiceoverCatalogItem = {
  id: number;
  name: string;
  /** Серий в ленте за popular_days дней */
  releases: number;
  subscriptions: number;
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
  source?: SourceId;
  source_id?: string | null;
  last_episode?: string | null;
  total_episodes?: number | null;
  next_episode?: NextEpisodeForecast | null;
  ratings?: RatingItem[];
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
  ratings?: RatingItem[];
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
