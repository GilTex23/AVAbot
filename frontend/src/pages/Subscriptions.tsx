import { ExternalLink, Loader2, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LazyImage } from "../components/ui/LazyImage";
import { deleteSubscription, getSubscriptions } from "../services/api";
import type { SubscriptionItem } from "../lib/types";
import { hapticNotification } from "../lib/telegram";
import { openAnime } from "../lib/utils";

type SubscriptionsProps = {
  refreshKey: number;
};

export function Subscriptions({ refreshKey }: SubscriptionsProps) {
  const [items, setItems] = useState<SubscriptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotice(null);
    getSubscriptions()
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setNotice("Не удалось загрузить подписки. Попробуйте обновить страницу.");
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

  async function removeSubscription(id: number) {
    setPendingDeleteId(id);
    setNotice(null);
    try {
      await deleteSubscription(id);
      setItems((current) => current.filter((item) => item.id !== id));
      hapticNotification("success");
      setNotice("Подписка удалена.");
    } catch {
      hapticNotification("error");
      setNotice("Не удалось удалить подписку. Попробуйте ещё раз.");
    } finally {
      setPendingDeleteId(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Мои подписки</h1>
        <p>{items.length} активных тайтла</p>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <div className="compact-list">
        {loading ? (
          <Card className="empty-state">
            <Loader2 className="spin" size={24} />
            Загружаю подписки...
          </Card>
        ) : (
          items.map((item) => (
            <Card key={item.id} className="subscription-row">
              <LazyImage className="subscription-row__poster" src={item.poster_url || undefined} alt={item.title} />
              <div className="subscription-row__main">
                <h2>{item.title}</h2>
                <div className="subscription-row__meta">
                  <Badge tone="red">{item.voiceover}</Badge>
                  <span>
                    {item.last_episode || "Серия ?"} / {item.total_episodes || "?"}
                  </span>
                </div>
              </div>
              <div className="subscription-row__actions">
                <Button size="icon" variant="ghost" aria-label="Открыть" onClick={() => openAnime(item.link)}>
                  <ExternalLink size={18} />
                </Button>
                <Button size="icon" variant="danger" disabled={pendingDeleteId === item.id} aria-label="Удалить" onClick={() => removeSubscription(item.id)}>
                  {pendingDeleteId === item.id ? <Loader2 className="spin" size={18} /> : <Trash2 size={18} />}
                </Button>
              </div>
            </Card>
          ))
        )}
      </div>

      {!loading && items.length === 0 ? <Card className="empty-state">Подписок пока нет. Добавьте тайтл из обновлений или расписания.</Card> : null}
    </div>
  );
}
