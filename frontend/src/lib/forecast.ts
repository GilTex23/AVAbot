import type { NextEpisodeForecast } from "./types";

const HOUR = 60 * 60 * 1000;

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function formatDay(date: Date) {
  return date.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "short" });
}

function formatShortDay(date: Date) {
  return date.toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
}

function formatTime(date: Date) {
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

/** «сб, 14 сент., около 21:00», «сб, 14 сент.» или «13–15 сент.» — в зависимости от разброса */
export function formatForecastWindow(forecast: NextEpisodeForecast) {
  const earliest = new Date(forecast.earliest_at);
  const latest = new Date(forecast.latest_at);
  const expected = new Date(forecast.expected_at);

  if (latest.getTime() - earliest.getTime() <= 3 * HOUR) {
    return `${formatDay(expected)}, около ${formatTime(expected)}`;
  }
  if (sameDay(earliest, latest)) {
    return formatDay(expected);
  }
  if (earliest.getFullYear() === latest.getFullYear() && earliest.getMonth() === latest.getMonth()) {
    return `${earliest.getDate()}–${formatShortDay(latest)}`;
  }
  return `${formatShortDay(earliest)} – ${formatShortDay(latest)}`;
}

function formatLag(hours: number) {
  if (hours < 1) {
    return "меньше часа";
  }
  if (hours < 24) {
    return `~${Math.round(hours)} ч`;
  }
  const days = Math.round((hours / 24) * 2) / 2;
  return `~${days.toLocaleString("ru-RU")} ${pluralDays(days)}`;
}

function pluralDays(days: number) {
  if (!Number.isInteger(days)) {
    return "дня";
  }
  const mod10 = days % 10;
  const mod100 = days % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return "день";
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return "дня";
  }
  return "дней";
}

/** Пояснение, откуда взялся прогноз */
export function describeForecast(forecast: NextEpisodeForecast) {
  const airText = forecast.air_at ? `${forecast.air_estimated ? "примерно " : ""}${formatDay(new Date(forecast.air_at))}, ${formatTime(new Date(forecast.air_at))}` : null;

  switch (forecast.basis) {
    case "title":
      return `Оригинал ${airText}; эта озвучка обычно через ${formatLag(forecast.lag_hours ?? 0)}`;
    case "studio":
      return `Оригинал ${airText}; студия по другим тайтлам — через ${formatLag(forecast.lag_hours ?? 0)}`;
    case "cadence":
      return "По обычному интервалу между сериями в этой озвучке";
    case "airing":
      return "Выход оригинала — первые озвучки обычно появляются вскоре после него";
  }
}
