import { CalendarClock, ExternalLink, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { NextEpisode } from "../components/NextEpisode";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LazyImage } from "../components/ui/LazyImage";
import { getMyWeek } from "../services/api";
import type { WeekItem } from "../lib/types";
import { openAnime } from "../lib/utils";

type MyWeekProps = {
  refreshKey: number;
};

type WeekGroup = {
  key: string;
  title: string;
  items: WeekItem[];
};

function dayKey(date: Date) {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function dayTitle(date: Date) {
  const today = new Date();
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  if (dayKey(date) === dayKey(today)) {
    return "Сегодня";
  }
  if (dayKey(date) === dayKey(tomorrow)) {
    return "Завтра";
  }
  const title = date.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
  return title.charAt(0).toUpperCase() + title.slice(1);
}

/** Задерживающиеся — сверху, остальное по дням (в часовом поясе устройства) */
function groupByDay(items: WeekItem[]): WeekGroup[] {
  const groups: WeekGroup[] = [];
  const overdue = items.filter((item) => item.forecast.overdue);
  if (overdue.length) {
    groups.push({ key: "overdue", title: "Задерживаются", items: overdue });
  }
  for (const item of items.filter((entry) => !entry.forecast.overdue)) {
    const date = new Date(item.forecast.expected_at);
    const key = dayKey(date);
    const group = groups.find((entry) => entry.key === key);
    if (group) {
      group.items.push(item);
    } else {
      groups.push({ key, title: dayTitle(date), items: [item] });
    }
  }
  return groups;
}

export function MyWeek({ refreshKey }: MyWeekProps) {
  const [items, setItems] = useState<WeekItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const groups = useMemo(() => groupByDay(items), [items]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    getMyWeek()
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNotice("Не удалось загрузить прогнозы. Попробуйте обновить страницу.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (loading) {
    return (
      <Card className="empty-state">
        <Loader2 className="spin" size={24} />
        Считаю прогнозы...
      </Card>
    );
  }

  return (
    <div className="schedule-days">
      {notice ? <div className="notice">{notice}</div> : null}

      {groups.map((group) => (
        <section key={group.key} className="schedule-day">
          <div className="schedule-day__head">
            <h2 className={group.key === "overdue" ? "week-overdue-title" : undefined}>{group.title}</h2>
            <Badge tone={group.key === "overdue" ? "amber" : "muted"}>{group.items.length}</Badge>
          </div>
          <div className="compact-list">
            {group.items.map((item) => (
              <Card key={`${item.id}-${item.forecast.episode}`} className="subscription-row">
                <LazyImage className="subscription-row__poster" src={item.poster_url || undefined} alt={item.title} />
                <div className="subscription-row__main">
                  <h2>{item.title}</h2>
                  <div className="subscription-row__meta">
                    <Badge tone="red">{item.voiceover}</Badge>
                  </div>
                  <NextEpisode forecast={item.forecast} />
                </div>
                <div className="subscription-row__actions">
                  <Button size="icon" variant="ghost" aria-label="Открыть" onClick={() => openAnime(item.link)}>
                    <ExternalLink size={18} />
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </section>
      ))}

      {!notice && groups.length === 0 ? (
        <Card className="empty-state">
          <CalendarClock size={24} />
          На ближайшую неделю прогнозов нет. Они появляются, когда по тайтлу накопится история выходов — обычно после одной-двух серий.
        </Card>
      ) : null}
    </div>
  );
}
