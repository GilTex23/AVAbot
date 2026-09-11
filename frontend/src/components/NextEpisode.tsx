import { CalendarClock } from "lucide-react";
import { describeForecast, formatForecastWindow } from "../lib/forecast";
import type { NextEpisodeForecast } from "../lib/types";
import { cx } from "../lib/utils";

export function NextEpisode({ forecast }: { forecast: NextEpisodeForecast }) {
  const when = formatForecastWindow(forecast);
  return (
    <div className={cx("subscription-forecast", forecast.overdue && "subscription-forecast--overdue")}>
      <CalendarClock size={14} />
      <div>
        <span className="subscription-forecast__main">
          {forecast.overdue ? `Серия ${forecast.episode} задерживается — ждали ${when}` : `Серия ${forecast.episode} ≈ ${when}`}
        </span>
        <span className="subscription-forecast__hint">{describeForecast(forecast)}</span>
      </div>
    </div>
  );
}
