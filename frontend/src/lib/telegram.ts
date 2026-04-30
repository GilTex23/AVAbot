type TelegramWebApp = {
  initData?: string;
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

export function getTelegramWebApp() {
  return window.Telegram?.WebApp;
}

export function getTelegramInitData() {
  return getTelegramWebApp()?.initData || "";
}

export function isTelegramMiniApp() {
  return Boolean(getTelegramInitData()) || Boolean(import.meta.env.VITE_DEV_TG_ID);
}

export function bootTelegramShell() {
  const app = getTelegramWebApp();
  app?.ready?.();
  app?.expand?.();
  app?.MainButton?.hide();
}
