type TelegramWebApp = {
  initData?: string;
  initDataUnsafe?: {
    user?: {
      id?: number;
      username?: string;
      first_name?: string;
      last_name?: string;
      photo_url?: string;
    };
    start_param?: string;
  };
  colorScheme?: "light" | "dark";
  ready?: () => void;
  expand?: () => void;
  MainButton?: {
    hide: () => void;
  };
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: TelegramWebApp;
    };
  }
}

const INIT_DATA_STORAGE_KEY = "miniapp-telegram-init-data";

export function getTelegramWebApp() {
  return window.Telegram?.WebApp;
}

function normalizeHashSource(hash: string) {
  const cleanHash = hash.replace(/^#\/?/, "");
  return cleanHash.startsWith("?") ? cleanHash : `?${cleanHash}`;
}

function getTelegramInitDataFromUrl() {
  const searchParams = new URLSearchParams(window.location.search);
  const searchData = searchParams.get("tgWebAppData") || searchParams.get("initData");
  if (searchData) {
    return searchData;
  }

  if (!window.location.hash) {
    return "";
  }

  const hashParams = new URLSearchParams(normalizeHashSource(window.location.hash));
  return hashParams.get("tgWebAppData") || hashParams.get("initData") || "";
}

export function getTelegramInitData() {
  const initData = getTelegramWebApp()?.initData || getTelegramInitDataFromUrl() || sessionStorage.getItem(INIT_DATA_STORAGE_KEY) || "";
  if (initData) {
    sessionStorage.setItem(INIT_DATA_STORAGE_KEY, initData);
  }
  return initData;
}

export function isTelegramMiniApp() {
  return Boolean(getTelegramInitData()) || Boolean(import.meta.env.VITE_DEV_TG_ID);
}

export function bootTelegramShell() {
  const app = getTelegramWebApp();
  getTelegramInitData();
  app?.ready?.();
  app?.expand?.();
  app?.MainButton?.hide();
}
