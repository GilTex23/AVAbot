import { Check, ExternalLink, Loader2, Plus, Radio, Star } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LazyImage } from "../components/ui/LazyImage";
import { YummySearch } from "../components/YummySearch";
import { addSubscription, errorText, getSubscriptions, getUpdates } from "../services/api";
import type { SourceId, SubscriptionItem, UpdateItem, UpdatesResponse } from "../lib/types";
import { buildSubscriptionIndex, subscriptionKey } from "../lib/subscriptions";
import { hapticNotification } from "../lib/telegram";
import { ALL_VOICEOVERS, describeVoiceovers, openAnime } from "../lib/utils";

type UpdatesProps = {
  favoriteVoiceovers: string[];
  refreshKey: number;
};

export function Updates({ favoriteVoiceovers, refreshKey }: UpdatesProps) {
  // null — любимые озвучки (если их нет, сервер отдаёт все), ALL_VOICEOVERS — все, иначе одна озвучка
  const [selectedVoiceover, setSelectedVoiceover] = useState<string | null>(null);
  const [source, setSource] = useState<SourceId>("animego");
  const [studios, setStudios] = useState<UpdatesResponse["studios"]>([]);
  const [items, setItems] = useState<UpdateItem[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingLink, setPendingLink] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const subscriptionIndex = useMemo(() => buildSubscriptionIndex(subscriptions), [subscriptions]);
  const hasFavorites = favoriteVoiceovers.length > 0;
  const showsAll = selectedVoiceover === ALL_VOICEOVERS || (selectedVoiceover === null && !hasFavorites);
  const selectedLabel = selectedVoiceover === null ? describeVoiceovers(favoriteVoiceovers, 2) : selectedVoiceover === ALL_VOICEOVERS ? "Все озвучки" : selectedVoiceover;
  // Озвучки из ленты; выбранная остаётся в списке, даже если после обновления её серий в ленте не стало
  const studioChips = useMemo(() => {
    if (!selectedVoiceover || selectedVoiceover === ALL_VOICEOVERS || studios.some((studio) => studio.name === selectedVoiceover)) {
      return studios;
    }
    return [...studios, { name: selectedVoiceover, count: 0 }];
  }, [studios, selectedVoiceover]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    Promise.all([getUpdates(selectedVoiceover, source), getSubscriptions()])
      .then(([updatesData, subscriptionsData]) => {
        if (!cancelled) {
          setItems(updatesData.items);
          setStudios(updatesData.studios);
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
  }, [selectedVoiceover, source, refreshKey, reloadKey]);

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
            source: item.source,
            source_id: item.source_id,
            last_episode: item.episode,
            total_episodes: null,
          },
        ]);
      }
      hapticNotification(result.created ? "success" : "warning");
      setNotice(result.created ? "Подписка добавлена." : "Такая подписка уже есть.");
    } catch (error) {
      hapticNotification("error");
      setNotice(errorText(error, "Не удалось оформить подписку. Попробуйте ещё раз."));
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
        <Badge tone="red" className="hero-panel__badge">
          <span className="badge__text">{selectedLabel}</span>
        </Badge>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <div className="source-switch" role="tablist" aria-label="Источник">
        {(["animego", "yummy"] as SourceId[]).map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={source === value}
            className={source === value ? "source-switch__item source-switch__item--active" : "source-switch__item"}
            onClick={() => {
              setSource(value);
              setStudios([]);
              setSelectedVoiceover(null);
            }}
          >
            {value === "animego" ? "AnimeGO" : "YummyAnime"}
          </button>
        ))}
      </div>

      {source === "yummy" ? <YummySearch subscriptions={subscriptions} onSubscribed={() => setReloadKey((value) => value + 1)} /> : null}

      <div className="chip-row" aria-label="Фильтр озвучки">
        {hasFavorites ? (
          <button className={selectedVoiceover === null ? "chip chip--active" : "chip"} type="button" onClick={() => setSelectedVoiceover(null)}>
            ★ Любимые
          </button>
        ) : null}
        <button className={showsAll ? "chip chip--active" : "chip"} type="button" onClick={() => setSelectedVoiceover(ALL_VOICEOVERS)}>
          {ALL_VOICEOVERS}
        </button>
        {studioChips.map((studio) => (
          <button
            key={studio.name}
            className={studio.name === selectedVoiceover ? "chip chip--active" : "chip"}
            type="button"
            onClick={() => setSelectedVoiceover(studio.name)}
          >
            {studio.name}
            {studio.count ? <span className="chip__count">{studio.count}</span> : null}
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
                    <span className="studio-pill" title={item.studio}>
                      {item.studio}
                    </span>
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
          {selectedVoiceover === null && hasFavorites ? "Для любимых озвучек свежих серий пока нет." : "Для этой озвучки свежих серий пока нет."}
        </Card>
      ) : null}
    </div>
  );
}
