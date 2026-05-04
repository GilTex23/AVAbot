import { Check, Clock, ExternalLink, Loader2, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LazyImage } from "../components/ui/LazyImage";
import { addScheduleSubscription, getAnimeDetails, getSchedule, getSubscriptions } from "../services/api";
import type { AnimeDetails, ScheduleDay, ScheduleItem, SubscriptionItem } from "../lib/types";
import { buildSubscriptionIndex, normalizeAnimeLink, subscriptionKey } from "../lib/subscriptions";
import { hapticNotification } from "../lib/telegram";
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
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [pendingLink, setPendingLink] = useState<string | null>(null);
  const [pendingVoiceover, setPendingVoiceover] = useState<string | null>(null);
  const [modal, setModal] = useState<VoiceoverModal | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const subscriptionIndex = useMemo(() => buildSubscriptionIndex(subscriptions), [subscriptions]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    Promise.all([getSchedule(), getSubscriptions()])
      .then(([scheduleData, subscriptionsData]) => {
        if (!cancelled) {
          setDays(scheduleData.days);
          setSubscriptions(subscriptionsData.items);
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
        hapticNotification("warning");
        setNotice("Этот тайтл уже полностью вышел, подписка не нужна.");
        return;
      }
      if (details.type?.toLowerCase().includes("фильм")) {
        hapticNotification("warning");
        setNotice("На фильмы подписка не оформляется, новых серий у них не будет.");
        return;
      }
      if (!details.voiceovers.length) {
        hapticNotification("warning");
        setNotice("Для этого тайтла не удалось найти доступные озвучки.");
        return;
      }
      setModal({ item, details });
    } catch {
      hapticNotification("error");
      setNotice("Не удалось получить список озвучек. Попробуйте ещё раз.");
    } finally {
      setPendingLink(null);
    }
  }

  async function subscribeFromSchedule(voiceover: string) {
    if (!modal) {
      return;
    }
    setPendingVoiceover(voiceover);
    setNotice(null);
    try {
      const result = await addScheduleSubscription(modal.item, voiceover, modal.details.total_episodes);
      if (result.created) {
        const tempId = Number(`${Date.now()}${Math.floor(Math.random() * 1000)}`);
        setSubscriptions((current) => [
          ...current,
          {
            id: tempId,
            title: modal.item.title,
            link: modal.item.link,
            poster_url: modal.item.poster_url,
            voiceover,
            last_episode: "Серия 0",
            total_episodes: modal.details.total_episodes,
          },
        ]);
      }
      hapticNotification(result.created ? "success" : "warning");
      setNotice(result.created ? "Подписка добавлена." : "Такая подписка уже есть.");
      setModal(null);
    } catch {
      hapticNotification("error");
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
                  const animeSubscriptions = subscriptionIndex.byAnime.get(normalizeAnimeLink(item.link)) || [];
                  const subscribedVoiceovers = animeSubscriptions.map((subscription) => subscription.voiceover);
                  const isPending = pendingLink === item.link;
                  const isAlreadySelected = subscribedVoiceovers.length > 0;
                  return (
                    <Card key={`${day.date_str}-${item.link}-${item.time}`} className="schedule-row">
                      <LazyImage className="schedule-row__poster" src={item.poster_url} alt={item.title} />
                      <div className="schedule-row__body">
                        <Badge tone="muted">
                          <Clock size={14} />
                          {item.time || "В течение дня"}
                        </Badge>
                        <h2>{item.title}</h2>
                        {subscribedVoiceovers.length ? (
                          <div className="subscription-chips" aria-label="Уже добавленные озвучки">
                            {subscribedVoiceovers.slice(0, 2).map((voiceover) => (
                              <span key={voiceover}>{voiceover}</span>
                            ))}
                            {subscribedVoiceovers.length > 2 ? <span>+{subscribedVoiceovers.length - 2}</span> : null}
                          </div>
                        ) : null}
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
                <Button
                  key={voiceover}
                  className="voiceover-option"
                  variant={subscriptionIndex.byAnimeVoiceover.has(subscriptionKey(modal.item.link, voiceover)) ? "secondary" : "primary"}
                  disabled={pendingVoiceover === voiceover || subscriptionIndex.byAnimeVoiceover.has(subscriptionKey(modal.item.link, voiceover))}
                  onClick={() => subscribeFromSchedule(voiceover)}
                >
                  {pendingVoiceover === voiceover ? <Loader2 className="spin" size={16} /> : subscriptionIndex.byAnimeVoiceover.has(subscriptionKey(modal.item.link, voiceover)) ? <Check size={16} /> : <Plus size={16} />}
                  <span>{voiceover}</span>
                  {subscriptionIndex.byAnimeVoiceover.has(subscriptionKey(modal.item.link, voiceover)) ? <small>уже добавлено</small> : null}
                </Button>
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
