import { ExternalLink, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { deleteSubscription, getSubscriptions } from "../services/api";
import type { SubscriptionItem } from "../lib/types";
import { openAnime } from "../lib/utils";

type SubscriptionsProps = {
  refreshKey: number;
};

export function Subscriptions({ refreshKey }: SubscriptionsProps) {
  const [items, setItems] = useState<SubscriptionItem[]>([]);

  useEffect(() => {
    getSubscriptions().then((data) => setItems(data.items));
  }, [refreshKey]);

  async function removeSubscription(id: number) {
    await deleteSubscription(id);
    setItems((current) => current.filter((item) => item.id !== id));
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Мои подписки</h1>
        <p>{items.length} активных тайтла</p>
      </section>

      <div className="compact-list">
        {items.map((item) => (
          <Card key={item.id} className="subscription-row">
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
              <Button size="icon" variant="danger" aria-label="Удалить" onClick={() => removeSubscription(item.id)}>
                <Trash2 size={18} />
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {items.length === 0 ? <Card className="empty-state">Подписок пока нет. Добавь тайтл из обновлений или расписания.</Card> : null}
    </div>
  );
}
