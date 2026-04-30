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
