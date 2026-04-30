export type Voiceover = "AniLiberty" | "AniDUB" | "Dream Cast" | "SHIZA Project" | "AnimeVost" | "Все" | string;

export type UserProfile = {
  id: number;
  username?: string | null;
  favorite_voiceover?: string | null;
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

export type ScheduleDay = {
  date_str: string;
  items: ScheduleItem[];
};

export type TabId = "updates" | "subscriptions" | "schedule" | "settings";
