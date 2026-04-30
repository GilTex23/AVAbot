import { Clock, ExternalLink, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LazyImage } from "../components/ui/LazyImage";
import { getSchedule } from "../services/api";
import type { ScheduleDay } from "../lib/types";
import { openAnime } from "../lib/utils";

type ScheduleProps = {
  refreshKey: number;
};

export function Schedule({ refreshKey }: ScheduleProps) {
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [query, setQuery] = useState("");

  useEffect(() => {
    getSchedule().then((data) => setDays(data.days));
  }, [refreshKey]);

  const filteredDays = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      return days;
    }
    return days
      .map((day) => ({
        ...day,
        items: day.items.filter((item) => item.title.toLowerCase().includes(normalized)),
      }))
      .filter((day) => day.items.length > 0);
  }, [days, query]);

  return (
    <div className="page-stack">
      <section className="section-title">
        <div>
          <h1>Расписание</h1>
          <p>Все дни недели с поиском по тайтлам</p>
        </div>
      </section>

      <label className="search-field">
        <Search size={18} />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти в расписании" />
      </label>

      <div className="schedule-days">
        {filteredDays.map((day, dayIndex) => (
          <section key={`${day.date_str}-${dayIndex}`} className="schedule-day">
            <div className="schedule-day__head">
              <h2>{day.date_str}</h2>
              <Badge tone="muted">{day.items.length}</Badge>
            </div>
            <div className="compact-list">
              {day.items.map((item) => (
                <Card key={`${day.date_str}-${item.link}-${item.time}`} className="schedule-row">
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
          </section>
        ))}
      </div>

      {days.length === 0 ? <Card className="empty-state">Расписание пока не загружено.</Card> : null}
      {days.length > 0 && filteredDays.length === 0 ? <Card className="empty-state">По этому запросу ничего не найдено.</Card> : null}
    </div>
  );
}
