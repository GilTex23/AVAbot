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

export type SubscriptionItem = {
  id: number;
  title: string;
  link: string;
  poster_url?: string | null;
  voiceover: string;
  last_episode?: string | null;
  total_episodes?: number | null;
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
};

export type NewScraperKey = {
  name: string;
  email: string;
  key: string;
};

export type ScraperKeyPatch = Partial<{ name: string; email: string; enabled: boolean }>;
