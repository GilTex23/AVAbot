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
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  openLink?: (url: string, options?: { try_instant_view?: boolean }) => void;
  openTelegramLink?: (url: string) => void;
  showAlert?: (message: string, callback?: () => void) => void;
  requestWriteAccess?: (callback?: (granted: boolean) => void) => void;
  HapticFeedback?: {
    impactOccurred?: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
    notificationOccurred?: (type: "error" | "success" | "warning") => void;
    selectionChanged?: () => void;
  };
  MainButton?: {
    hide: () => void;
  };
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
    offClick: (callback: () => void) => void;
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
const WRITE_ACCESS_STORAGE_PREFIX = "miniapp-write-access:";

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
  const initData = getTelegramWebApp()?.initData || getTelegramInitDataFromUrl() || safeSessionStorageGet(INIT_DATA_STORAGE_KEY) || "";
  if (initData) {
    safeSessionStorageSet(INIT_DATA_STORAGE_KEY, initData);
  }
  return initData;
}

export function isTelegramMiniApp() {
  return Boolean(getTelegramInitData()) || Boolean(import.meta.env.VITE_DEV_TG_ID);
}

export function bootTelegramShell() {
  const app = getTelegramWebApp();
  getTelegramInitData();
  app?.setHeaderColor?.("#242525");
  app?.setBackgroundColor?.("#141515");
  app?.ready?.();
  app?.expand?.();
  app?.MainButton?.hide();
}

export function openTelegramLink(url: string) {
  const app = getTelegramWebApp();
  if (app?.openLink) {
    app.openLink(url);
    return;
  }
  window.open(url, "_blank", "noopener,noreferrer");
}

/** Ссылки t.me внутри Telegram открываются без браузера: окно «Поделиться», чат с ботом */
export function openTelegramChatLink(url: string) {
  const app = getTelegramWebApp();
  if (app?.openTelegramLink) {
    app.openTelegramLink(url);
    return;
  }
  openTelegramLink(url);
}

export function showTelegramAlert(message: string) {
  const app = getTelegramWebApp();
  if (app?.showAlert) {
    app.showAlert(message);
    return;
  }
  window.alert(message);
}

// Экраны вкладываются (админка → статистика → график на весь экран): кнопка «Назад» закрывает только верхний
const backHandlers: Array<() => void> = [];

function dispatchBack() {
  backHandlers[backHandlers.length - 1]?.();
}

/** Показывает системную кнопку «Назад» Telegram для текущего экрана; возвращает функцию, которая снимает обработчик */
export function showTelegramBackButton(onBack: () => void) {
  const backButton = getTelegramWebApp()?.BackButton;
  if (!backButton) {
    return () => {};
  }
  backHandlers.push(onBack);
  if (backHandlers.length === 1) {
    backButton.onClick(dispatchBack);
    backButton.show();
  }
  return () => {
    const index = backHandlers.lastIndexOf(onBack);
    if (index >= 0) {
      backHandlers.splice(index, 1);
    }
    if (!backHandlers.length) {
      backButton.offClick(dispatchBack);
      backButton.hide();
    }
  };
}

export function hapticImpact(style: "light" | "medium" | "heavy" | "rigid" | "soft" = "light") {
  getTelegramWebApp()?.HapticFeedback?.impactOccurred?.(style);
}

export function hapticNotification(type: "error" | "success" | "warning") {
  getTelegramWebApp()?.HapticFeedback?.notificationOccurred?.(type);
}

export function requestWriteAccessOnce() {
  const app = getTelegramWebApp();
  const telegramId = app?.initDataUnsafe?.user?.id;
  if (!telegramId || typeof app?.requestWriteAccess !== "function") {
    return;
  }

  const storageKey = `${WRITE_ACCESS_STORAGE_PREFIX}${telegramId}`;
  if (safeLocalStorageGet(storageKey) === "true") {
    return;
  }

  app.requestWriteAccess((granted) => {
    if (granted) {
      safeLocalStorageSet(storageKey, "true");
      hapticNotification("success");
    }
  });
}

function safeSessionStorageGet(key: string) {
  try {
    return sessionStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function safeSessionStorageSet(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    // Storage is optional here because initData still goes out with the current request.
  }
}

function safeLocalStorageGet(key: string) {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function safeLocalStorageSet(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Write-access prompt can safely appear again if persistence is blocked.
  }
}
