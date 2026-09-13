import { Check, ExternalLink, Loader2, Plus, Search, Share2, X } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { LazyImage } from "./ui/LazyImage";
import { buildSubscriptionIndex, subscriptionKey } from "../lib/subscriptions";
import { hapticNotification } from "../lib/telegram";
import type { SubscriptionItem, YummyTitle, YummyTitleDetails } from "../lib/types";
import { openAnime, shareTitle, titleDeepLink } from "../lib/utils";
import { addYummySubscription, errorText, getYummyAnime, searchYummy } from "../services/api";

const statusLabels: Record<string, string> = { ongoing: "онгоинг", released: "вышел", anons: "анонс", announcement: "анонс" };

export function describeYummyTitle(title: Pick<YummyTitle, "kind" | "year" | "status" | "episodes_aired" | "total_episodes">) {
  const episodes = title.total_episodes || title.episodes_aired ? `${title.episodes_aired ?? 0} / ${title.total_episodes ?? "?"} сер.` : null;
  return [title.kind, title.year, title.status ? statusLabels[title.status] ?? title.status : null, episodes].filter(Boolean).join(" · ");
}

type YummySearchProps = {
  subscriptions: SubscriptionItem[];
  onSubscribed: () => void;
};

/** Поиск тайтла на YummyAnime и подписка на озвучку оттуда */
export function YummySearch({ subscriptions, onSubscribed }: YummySearchProps) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<YummyTitle[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [details, setDetails] = useState<YummyTitleDetails | null>(null);
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [pendingVoiceover, setPendingVoiceover] = useState<string | null>(null);
  const subscriptionIndex = useMemo(() => buildSubscriptionIndex(subscriptions), [subscriptions]);

  // Поиск сам запускается через полсекунды после ввода
  useEffect(() => {
    const text = query.trim();
    if (text.length < 2) {
      setResults(null);
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setSearching(true);
      setNotice(null);
      searchYummy(text)
        .then((data) => {
          if (!cancelled) {
            setResults(data.items);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setNotice(errorText(error, "YummyAnime сейчас не отвечает. Попробуйте позже."));
          }
        })
        .finally(() => {
          if (!cancelled) {
            setSearching(false);
          }
        });
    }, 500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query]);

  async function openTitle(title: YummyTitle) {
    setLoadingId(title.id);
    setNotice(null);
    try {
      setDetails(await getYummyAnime(title.id));
    } catch (error) {
      hapticNotification("error");
      setNotice(errorText(error, "Не удалось загрузить озвучки. Попробуйте ещё раз."));
    } finally {
      setLoadingId(null);
    }
  }

  async function subscribe(voiceover: string) {
    if (!details) {
      return;
    }
    setPendingVoiceover(voiceover);
    setNotice(null);
    try {
      const result = await addYummySubscription(details.id, voiceover);
      hapticNotification(result.created ? "success" : "warning");
      setNotice(result.created ? `Подписка на «${details.title}» (${voiceover}) добавлена.` : "Такая подписка уже есть.");
      setDetails(null);
      onSubscribed();
    } catch (error) {
      hapticNotification("error");
      setNotice(errorText(error, "Не удалось оформить подписку. Попробуйте ещё раз."));
    } finally {
      setPendingVoiceover(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setQuery((value) => value.trim());
  }

  return (
    <Card className="settings-card settings-card--column yummy-search">
      <div>
        <h2>Найти на YummyAnime</h2>
        <p className="muted-copy">Подписка на озвучку с YummyAnime — уведомления придут, когда серия появится там.</p>
      </div>
      <form className="search-field" onSubmit={submit}>
        <Search size={18} />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Название аниме" enterKeyHint="search" />
      </form>

      {notice && !details ? <div className="notice">{notice}</div> : null}
      {searching ? (
        <p className="muted-copy">
          <Loader2 className="spin" size={15} /> Ищу...
        </p>
      ) : null}
      {results && !searching && !results.length ? <p className="muted-copy">Ничего не найдено.</p> : null}

      {results?.length ? (
        <div className="compact-list">
          {results.map((title) => (
            <button key={title.id} type="button" className="yummy-result" onClick={() => openTitle(title)} disabled={loadingId !== null}>
              <LazyImage className="yummy-result__poster" src={title.poster_url || undefined} alt={title.title} />
              <span className="yummy-result__body">
                <span className="yummy-result__title">{title.title}</span>
                <span className="muted-copy">{describeYummyTitle(title)}</span>
              </span>
              {loadingId === title.id ? <Loader2 className="spin" size={18} /> : <Plus size={18} />}
            </button>
          ))}
        </div>
      ) : null}

      {details ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setDetails(null)}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-label="Выбор озвучки" onClick={(event) => event.stopPropagation()}>
            <div className="modal-card__head">
              <div>
                <h2>{details.title}</h2>
                <p>{describeYummyTitle(details)}</p>
              </div>
              <div className="modal-card__actions">
                {titleDeepLink(details.url, "yummy", String(details.id)) ? (
                  <Button size="icon" variant="ghost" aria-label="Поделиться" onClick={() => shareTitle(details.url, details.title, "yummy", String(details.id))}>
                    <Share2 size={18} />
                  </Button>
                ) : null}
                <Button size="icon" variant="ghost" aria-label="Открыть на YummyAnime" onClick={() => openAnime(details.url)}>
                  <ExternalLink size={18} />
                </Button>
                <Button size="icon" variant="ghost" aria-label="Закрыть" onClick={() => setDetails(null)}>
                  <X size={18} />
                </Button>
              </div>
            </div>
            {notice ? <div className="notice">{notice}</div> : null}
            {details.voiceovers.length ? (
              <div className="voiceover-list">
                {details.voiceovers.map((voiceover) => {
                  const subscribed = subscriptionIndex.byAnimeVoiceover.has(subscriptionKey(details.url, voiceover.name));
                  return (
                    <Button
                      key={voiceover.name}
                      className="voiceover-option"
                      variant={subscribed ? "secondary" : "primary"}
                      disabled={subscribed || pendingVoiceover !== null}
                      onClick={() => subscribe(voiceover.name)}
                    >
                      {pendingVoiceover === voiceover.name ? <Loader2 className="spin" size={16} /> : subscribed ? <Check size={16} /> : <Plus size={16} />}
                      <span>{voiceover.name}</span>
                      <small>{subscribed ? "уже добавлено" : `серия ${voiceover.last_episode}`}</small>
                    </Button>
                  );
                })}
              </div>
            ) : (
              <p className="muted-copy">На YummyAnime пока нет серий в озвучке.</p>
            )}
            <Badge tone="muted">Номер — последняя вышедшая серия в озвучке</Badge>
          </section>
        </div>
      ) : null}
    </Card>
  );
}
