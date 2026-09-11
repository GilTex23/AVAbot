import { createContext, useContext } from "react";

// Российские пояса — первыми внутри своего смещения (и запасной список, если браузер не отдаёт все пояса)
const russianTimeZones = [
  "Europe/Kaliningrad",
  "Europe/Moscow",
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

function supportedTimeZones() {
  const intlWithValues = Intl as typeof Intl & {
    supportedValuesOf?: (key: "timeZone") => string[];
  };
  if (typeof intlWithValues.supportedValuesOf === "function") {
    return intlWithValues.supportedValuesOf("timeZone");
  }
  return ["UTC", ...russianTimeZones];
}

/** Смещение пояса от UTC в минутах на указанный момент (с учётом летнего времени); null — пояс неизвестен */
export function timeZoneOffsetMinutes(timeZone: string, at: Date = new Date()) {
  try {
    const name = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "shortOffset" })
      .formatToParts(at)
      .find((part) => part.type === "timeZoneName")?.value;
    // «GMT», «GMT+3», «GMT-3:30»
    const match = name ? /^GMT(?:([+-])(\d{1,2})(?::(\d{2}))?)?$/.exec(name) : null;
    if (!match) {
      return null;
    }
    const minutes = Number(match[2] || 0) * 60 + Number(match[3] || 0);
    return match[1] === "-" ? -minutes : minutes;
  } catch {
    return null;
  }
}

export function formatOffset(minutes: number) {
  const hours = Math.floor(Math.abs(minutes) / 60);
  const rest = Math.abs(minutes) % 60;
  return `UTC${minutes < 0 ? "−" : "+"}${hours}${rest ? `:${String(rest).padStart(2, "0")}` : ""}`;
}

/**
 * Пояса по смещению от UTC (от −12 до +14), внутри смещения — сначала российские, потом по алфавиту.
 * extra — сохранённый пояс, которого может не быть в списке браузера.
 */
export function getTimeZones(extra?: string | null) {
  const now = new Date();
  const zones = new Set(supportedTimeZones());
  if (extra) {
    zones.add(extra);
  }
  return [...zones]
    .map((zone) => ({ zone, offset: timeZoneOffsetMinutes(zone, now) }))
    .filter((item): item is { zone: string; offset: number } => item.offset !== null)
    .sort((a, b) => {
      if (a.offset !== b.offset) {
        return a.offset - b.offset;
      }
      const russianA = russianTimeZones.indexOf(a.zone);
      const russianB = russianTimeZones.indexOf(b.zone);
      if (russianA !== russianB) {
        return (russianA === -1 ? Infinity : russianA) - (russianB === -1 ? Infinity : russianB);
      }
      return a.zone.localeCompare(b.zone);
    })
    .map((item) => item.zone);
}

/** «UTC+3 · Europe/Moscow»: смещение первым, чтобы по списку было удобно листать */
export function formatTimeZoneLabel(timeZone: string) {
  const offset = timeZoneOffsetMinutes(timeZone);
  return offset === null ? timeZone : `${formatOffset(offset)} · ${timeZone}`;
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
