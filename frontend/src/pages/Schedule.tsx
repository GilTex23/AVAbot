import { Clock, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LazyImage } from "../components/ui/LazyImage";
import { getSchedule } from "../services/api";
import type { ScheduleDay } from "../lib/types";
import { openAnime } from "../lib/utils";

type ScheduleProps = {
  refreshKey: number;
};

export function Schedule({ refreshKey }: ScheduleProps) {
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [activeDay, setActiveDay] = useState(0);

  useEffect(() => {
    getSchedule().then((data) => setDays(data.days));
  }, [refreshKey]);

  const currentDay = days[activeDay];

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Расписание</h1>
        <p>Выходы серий по дням</p>
      </section>

      <div className="chip-row">
        {days.map((day, index) => (
          <button key={`${day.date_str}-${index}`} className={index === activeDay ? "chip chip--active" : "chip"} type="button" onClick={() => setActiveDay(index)}>
            {day.date_str}
          </button>
        ))}
      </div>

      <div className="compact-list">
        {currentDay?.items.map((item) => (
          <Card key={`${item.link}-${item.time}`} className="schedule-row">
            <LazyImage className="schedule-row__poster" src={item.poster_url} alt={item.title} />
            <div className="schedule-row__body">
              <Badge tone="muted">
                <Clock size={14} />
                {item.time || "В течение дня"}
              </Badge>
              <h2>{item.title}</h2>
            </div>
            <Button size="icon" variant="ghost" aria-label="Открыть" onClick={() => openAnime(item.link)}>
              <ExternalLink size={18} />
            </Button>
          </Card>
        ))}
      </div>

      {!currentDay ? <Card className="empty-state">Расписание пока не загружено.</Card> : null}
    </div>
  );
}
