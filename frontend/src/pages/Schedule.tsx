import { Check, Clock, ExternalLink, Loader2, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LazyImage } from "../components/ui/LazyImage";
import { addScheduleSubscription, getAnimeDetails, getSchedule } from "../services/api";
import type { AnimeDetails, ScheduleDay, ScheduleItem } from "../lib/types";
import { openAnime } from "../lib/utils";

type ScheduleProps = {
  refreshKey: number;
};

type VoiceoverModal = {
  item: ScheduleItem;
  details: AnimeDetails;
};

export function Schedule({ refreshKey }: ScheduleProps) {
  const [days, setDays] = useState<ScheduleDay[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingLink, setPendingLink] = useState<string | null>(null);
  const [pendingVoiceover, setPendingVoiceover] = useState<string | null>(null);
  const [subscribedKeys, setSubscribedKeys] = useState<Set<string>>(() => new Set());
  const [modal, setModal] = useState<VoiceoverModal | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    getSchedule()
      .then((data) => {
        if (!cancelled) {
          setDays(data.days);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNotice("Не удалось загрузить расписание. Попробуйте обновить страницу.");
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

  async function openVoiceovers(item: ScheduleItem) {
    setPendingLink(item.link);
    setNotice(null);
    try {
      const details = await getAnimeDetails(item.link);
      if (details.status?.toLowerCase().includes("вышел")) {
        setNotice("Этот тайтл уже полностью вышел, подписка не нужна.");
        return;
      }
      if (details.type?.toLowerCase().includes("фильм")) {
        setNotice("На фильмы подписка не оформляется, новых серий у них не будет.");
        return;
      }
      if (!details.voiceovers.length) {
        setNotice("Для этого тайтла не удалось найти доступные озвучки.");
        return;
      }
      setModal({ item, details });
    } catch {
      setNotice("Не удалось получить список озвучек. Попробуйте ещё раз.");
    } finally {
      setPendingLink(null);
    }
  }

  async function subscribeFromSchedule(voiceover: string) {
    if (!modal) {
      return;
    }
    const key = `${modal.item.link}-${voiceover}`;
    setPendingVoiceover(voiceover);
    setNotice(null);
    try {
      const result = await addScheduleSubscription(modal.item, voiceover, modal.details.total_episodes);
      setSubscribedKeys((current) => new Set(current).add(key));
      setNotice(result.created ? "Подписка добавлена." : "Такая подписка уже есть.");
      setModal(null);
    } catch {
      setNotice("Не удалось оформить подписку. Попробуйте ещё раз.");
    } finally {
      setPendingVoiceover(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <div>
          <h1>Расписание</h1>
          <p>Все дни недели с поиском по тайтлам</p>
        </div>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <label className="search-field">
        <Search size={18} />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Найти в расписании" />
      </label>

      <div className="schedule-days">
        {loading ? (
          <Card className="empty-state">
            <Loader2 className="spin" size={24} />
            Загружаю расписание...
          </Card>
        ) : (
          filteredDays.map((day, dayIndex) => (
            <section key={`${day.date_str}-${dayIndex}`} className="schedule-day">
              <div className="schedule-day__head">
                <h2>{day.date_str}</h2>
                <Badge tone="muted">{day.items.length}</Badge>
              </div>
              <div className="compact-list">
                {day.items.map((item) => {
                  const isPending = pendingLink === item.link;
                  const isAlreadySelected = Array.from(subscribedKeys).some((key) => key.startsWith(`${item.link}-`));
                  return (
                    <Card key={`${day.date_str}-${item.link}-${item.time}`} className="schedule-row">
                      <LazyImage className="schedule-row__poster" src={item.poster_url} alt={item.title} />
                      <div className="schedule-row__body">
                        <Badge tone="muted">
                          <Clock size={14} />
                          {item.time || "В течение дня"}
                        </Badge>
                        <h2>{item.title}</h2>
                      </div>
                      <div className="schedule-row__actions">
                        <Button size="icon" variant={isAlreadySelected ? "secondary" : "primary"} disabled={isPending} aria-label="Подписаться" onClick={() => openVoiceovers(item)}>
                          {isPending ? <Loader2 className="spin" size={18} /> : isAlreadySelected ? <Check size={18} /> : <Plus size={18} />}
                        </Button>
                        <Button size="icon" variant="ghost" aria-label="Открыть" onClick={() => openAnime(item.link)}>
                          <ExternalLink size={18} />
                        </Button>
                      </div>
                    </Card>
                  );
                })}
              </div>
            </section>
          ))
        )}
      </div>

      {!loading && days.length === 0 ? <Card className="empty-state">Расписание пока не загружено.</Card> : null}
      {!loading && days.length > 0 && filteredDays.length === 0 ? <Card className="empty-state">По этому запросу ничего не найдено.</Card> : null}

      {modal ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setModal(null)}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="Выбор озвучки" onClick={(event) => event.stopPropagation()}>
            <div className="modal-card__head">
              <div>
                <h2>{modal.item.title}</h2>
                <p>Выберите озвучку для подписки</p>
              </div>
              <Button size="icon" variant="ghost" aria-label="Закрыть" onClick={() => setModal(null)}>
                <X size={18} />
              </Button>
            </div>
            <div className="voiceover-list">
              {modal.details.voiceovers.map((voiceover) => (
                <Button key={voiceover} variant="secondary" disabled={pendingVoiceover === voiceover} onClick={() => subscribeFromSchedule(voiceover)}>
                  {pendingVoiceover === voiceover ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
                  {voiceover}
                </Button>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
