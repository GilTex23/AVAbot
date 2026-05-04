import { Check, ExternalLink, Loader2, Plus, Radio, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LazyImage } from "../components/ui/LazyImage";
import { addSubscription, getSubscriptions, getUpdates } from "../services/api";
import type { SubscriptionItem, UpdateItem } from "../lib/types";
import { buildSubscriptionIndex, subscriptionKey } from "../lib/subscriptions";
import { hapticNotification } from "../lib/telegram";
import { openAnime, voiceovers } from "../lib/utils";

type UpdatesProps = {
  favoriteVoiceover: string;
  refreshKey: number;
};

export function Updates({ favoriteVoiceover, refreshKey }: UpdatesProps) {
  const [selectedVoiceover, setSelectedVoiceover] = useState(favoriteVoiceover || "AniLiberty");
  const [items, setItems] = useState<UpdateItem[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingLink, setPendingLink] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const subscriptionIndex = useMemo(() => buildSubscriptionIndex(subscriptions), [subscriptions]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    Promise.all([getUpdates(selectedVoiceover), getSubscriptions()])
      .then(([updatesData, subscriptionsData]) => {
        if (!cancelled) {
          setItems(updatesData.items);
          setSubscriptions(subscriptionsData.items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNotice("Не удалось загрузить обновления. Попробуйте обновить страницу.");
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
  }, [selectedVoiceover, refreshKey]);

  async function subscribe(item: UpdateItem) {
    const key = subscriptionKey(item.link, item.studio);
    setPendingLink(key);
    setNotice(null);
    try {
      const result = await addSubscription(item);
      if (result.created) {
        const tempId = Number(`${Date.now()}${Math.floor(Math.random() * 1000)}`);
        setSubscriptions((current) => [
          ...current,
          {
            id: tempId,
            title: item.title,
            link: item.link,
            poster_url: item.poster_url,
            voiceover: item.studio,
            last_episode: item.episode,
            total_episodes: null,
          },
        ]);
      }
      hapticNotification(result.created ? "success" : "warning");
      setNotice(result.created ? "Подписка добавлена." : "Такая подписка уже есть.");
    } catch {
      hapticNotification("error");
      setNotice("Не удалось оформить подписку. Попробуйте ещё раз.");
    } finally {
      setPendingLink(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <h1>Свежие серии</h1>
          <p>Постеры, озвучки и быстрый переход к тайтлу в одном экране.</p>
        </div>
        <Badge tone="red">{selectedVoiceover}</Badge>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <div className="chip-row" aria-label="Фильтр озвучки">
        {voiceovers.map((voiceover) => (
          <button key={voiceover} className={voiceover === selectedVoiceover ? "chip chip--active" : "chip"} type="button" onClick={() => setSelectedVoiceover(voiceover)}>
            {voiceover}
          </button>
        ))}
      </div>

      <div className="update-list">
        {loading ? (
          <Card className="empty-state">
            <Loader2 className="spin" size={24} />
            Загружаю обновления...
          </Card>
        ) : (
          items.map((item) => {
            const key = subscriptionKey(item.link, item.studio);
            const isPending = pendingLink === key;
            const isSubscribed = subscriptionIndex.byAnimeVoiceover.has(key);
            return (
              <Card key={`${item.link}-${item.episode}-${item.studio}`} className="anime-row">
                <LazyImage className="anime-row__poster" src={item.poster_url} alt={item.title} />
                <div className="anime-row__body">
                  <div className="anime-row__meta">
                    <Badge tone="green">{item.episode}</Badge>
                    <span className="studio-pill">{item.studio}</span>
                    {isSubscribed ? <span className="subscribed-mark">В подписках</span> : null}
                  </div>
                  <h2>{item.title}</h2>
                  <div className="anime-row__actions">
                    <Button size="sm" variant={isSubscribed ? "secondary" : "primary"} disabled={isPending || isSubscribed} onClick={() => subscribe(item)}>
                      {isPending ? <Loader2 className="spin" size={16} /> : isSubscribed ? <Check size={16} /> : <Plus size={16} />}
                      {isPending ? "Добавляю" : isSubscribed ? "Добавлено" : "Подписаться"}
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => openAnime(item.link)}>
                      <ExternalLink size={16} />
                      Открыть
                    </Button>
                  </div>
                </div>
                <Star className="anime-row__watermark" size={42} />
              </Card>
            );
          })
        )}
      </div>

      {!loading && items.length === 0 ? (
        <Card className="empty-state">
          <Radio size={26} />
          Для этой озвучки свежих серий пока нет.
        </Card>
      ) : null}
    </div>
  );
}
