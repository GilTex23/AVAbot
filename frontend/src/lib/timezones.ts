import { createContext, useContext } from "react";

const fallbackTimeZones = [
  "UTC",
  "Europe/Moscow",
  "Europe/Kaliningrad",
  "Europe/Samara",
  "Asia/Yekaterinburg",
  "Asia/Omsk",
  "Asia/Novosibirsk",
  "Asia/Krasnoyarsk",
  "Asia/Irkutsk",
  "Asia/Yakutsk",
  "Asia/Vladivostok",
  "Asia/Magadan",
  "Asia/Kamchatka",
];

export function getTimeZones() {
  const intlWithValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  if (typeof intlWithValues.supportedValuesOf === "function") {
    return intlWithValues.supportedValuesOf("timeZone");
  }
  return fallbackTimeZones;
}

export function formatTimeZoneLabel(timeZone: string) {
  try {
    const formatter = new Intl.DateTimeFormat("ru-RU", {
      timeZone,
      timeZoneName: "shortOffset",
      hour: "2-digit",
      minute: "2-digit",
    });
    const offset = formatter.formatToParts(new Date()).find((part) => part.type === "timeZoneName")?.value;
    return offset ? `${timeZone} (${offset})` : timeZone;
  } catch {
    return timeZone;
  }
}

export const DEFAULT_TIME_ZONE = "Europe/Moscow";

/** Часовой пояс из настроек пользователя: в нём показываются расписание и прогнозы */
export const TimeZoneContext = createContext(DEFAULT_TIME_ZONE);

export function useTimeZone() {
  return useContext(TimeZoneContext);
}

/** Пояс, который точно понимает Intl; иначе — Москва */
export function safeTimeZone(timeZone?: string | null) {
  if (!timeZone) {
    return DEFAULT_TIME_ZONE;
  }
  try {
    new Intl.DateTimeFormat("ru-RU", { timeZone });
    return timeZone;
  } catch {
    return DEFAULT_TIME_ZONE;
  }
}

/** Ключ календарного дня в поясе: «2026-09-11» */
export function dayKey(date: Date, timeZone: string) {
  return date.toLocaleDateString("en-CA", { timeZone });
}
