import { ArrowLeft, ChevronRight, ExternalLink, Loader2, Search, Trash2, UserRound } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ClampedTitle } from "../components/ClampedTitle";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { LazyImage } from "../components/ui/LazyImage";
import { describeAdminError } from "../lib/adminErrors";
import { hapticNotification, showTelegramBackButton } from "../lib/telegram";
import { formatTimeZoneLabel, useTimeZone } from "../lib/timezones";
import type { AdminUser, AdminUserDetails } from "../lib/types";
import { describeVoiceovers, openAnime } from "../lib/utils";
import { deleteAdminSubscription, getAdminUser, getAdminUsers } from "../services/api";

type AdminUsersProps = {
  refreshKey: number;
  onBack: () => void;
};

const PAGE_SIZE = 50;

function formatDay(iso: string | null | undefined, timeZone?: string) {
  if (!iso) {
    return "—";
  }
  // Дата без времени («2026-09-14») — день в UTC, как её пишет статистика
  const date = iso.length === 10 ? new Date(`${iso}T12:00:00Z`) : new Date(iso);
  const withYear = date.getUTCFullYear() !== new Date().getUTCFullYear();
  return date.toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    ...(withYear ? { year: "numeric" } : {}),
    timeZone: iso.length === 10 ? "UTC" : timeZone,
  });
}

function userName(user: Pick<AdminUser, "username" | "id">) {
  return user.username ? `@${user.username}` : `ID ${user.id}`;
}

export function AdminUsers({ refreshKey, onBack }: AdminUsersProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [updatedUser, setUpdatedUser] = useState<AdminUser | null>(null);
  const closeUser = useCallback(() => setSelectedId(null), []);

  return (
    <>
      <div hidden={selectedId !== null}>
        <UsersList refreshKey={refreshKey} onBack={onBack} onOpen={setSelectedId} active={selectedId === null} updatedUser={updatedUser} />
      </div>
      {selectedId !== null ? <UserDetails userId={selectedId} refreshKey={refreshKey} onBack={closeUser} onLoaded={setUpdatedUser} /> : null}
    </>
  );
}

type UsersListProps = {
  refreshKey: number;
  onBack: () => void;
  onOpen: (id: number) => void;
  active: boolean;
  /** Свежие данные пользователя из карточки (например, после удаления подписки) */
  updatedUser: AdminUser | null;
};

/** Список остаётся смонтированным под карточкой пользователя — поиск и прокрутка не сбрасываются */
function UsersList({ refreshKey, onBack, onOpen, active, updatedUser }: UsersListProps) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => (active ? showTelegramBackButton(onBack) : undefined), [onBack, active]);

  useEffect(() => {
    if (updatedUser) {
      setItems((current) => current.map((item) => (item.id === updatedUser.id ? { ...item, ...updatedUser } : item)));
    }
  }, [updatedUser]);

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      setLoading(true);
      setNotice(null);
      getAdminUsers(query.trim(), 0, PAGE_SIZE)
        .then((data) => {
          if (!cancelled) {
            setItems(data.items);
            setTotal(data.total);
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setNotice(describeAdminError(error, "Не удалось загрузить пользователей."));
          }
        })
        .finally(() => {
          if (!cancelled) {
            setLoading(false);
          }
        });
    }, query ? 400 : 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, refreshKey]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      const data = await getAdminUsers(query.trim(), items.length, PAGE_SIZE);
      setItems((current) => [...current, ...data.items]);
      setTotal(data.total);
    } catch (error) {
      setNotice(describeAdminError(error, "Не удалось загрузить пользователей."));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="admin-title">
        <Button size="icon" variant="ghost" aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} />
        </Button>
        <div>
          <h1>Пользователи</h1>
          <p>{loading ? "Загружаю..." : `${total} всего`}</p>
        </div>
      </section>

      <label className="search-field">
        <Search size={18} />
        <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Username или Telegram ID" />
      </label>

      {notice ? <div className="notice">{notice}</div> : null}

      {loading && !items.length ? (
        <Card className="empty-state">
          <Loader2 className="spin" size={24} />
          Загружаю пользователей...
        </Card>
      ) : null}
      {!loading && !items.length && !notice ? <Card className="empty-state">Никого не нашёл.</Card> : null}

      <div className="compact-list">
        {items.map((user) => (
          <button key={user.id} type="button" className="card admin-user-row" onClick={() => onOpen(user.id)}>
            {user.photo_url ? <img className="admin-user-row__avatar" src={user.photo_url} alt="" /> : <UserRound className="admin-user-row__avatar" size={22} />}
            <span className="admin-user-row__body">
              <span className="admin-user-row__name">
                {userName(user)}
                {user.is_admin ? <Badge tone="amber">админ</Badge> : null}
              </span>
              <span className="muted-copy">
                подписок: {user.subscriptions}
                {user.yummy_subscriptions ? ` (YummyAnime: ${user.yummy_subscriptions})` : ""} · заходил: {formatDay(user.last_active)}
              </span>
            </span>
            <ChevronRight size={18} />
          </button>
        ))}
      </div>

      {items.length < total ? (
        <Button variant="secondary" disabled={loadingMore} onClick={loadMore}>
          {loadingMore ? <Loader2 className="spin" size={16} /> : null}
          Показать ещё ({total - items.length})
        </Button>
      ) : null}
    </div>
  );
}

type UserDetailsProps = {
  userId: number;
  refreshKey: number;
  onBack: () => void;
  onLoaded: (user: AdminUser) => void;
};

function UserDetails({ userId, refreshKey, onBack, onLoaded }: UserDetailsProps) {
  const timeZone = useTimeZone();
  const [user, setUser] = useState<AdminUserDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  useEffect(() => showTelegramBackButton(onBack), [onBack]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [userId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAdminUser(userId)
      .then((data) => {
        if (!cancelled) {
          setUser(data);
          onLoaded(data);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(describeAdminError(error, "Не удалось загрузить пользователя."));
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
  }, [userId, refreshKey, onLoaded]);

  async function removeSubscription(id: number) {
    // Первое нажатие — подтверждение, второе — удаление
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      return;
    }
    setPendingDelete(id);
    setNotice(null);
    try {
      const updated = await deleteAdminSubscription(id);
      setUser(updated);
      onLoaded(updated);
      hapticNotification("success");
      setNotice("Подписка удалена.");
    } catch (error) {
      hapticNotification("error");
      setNotice(describeAdminError(error, "Не удалось удалить подписку."));
    } finally {
      setPendingDelete(null);
      setConfirmDelete(null);
    }
  }

  return (
    <div className="page-stack">
      <section className="admin-title">
        <Button size="icon" variant="ghost" aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} />
        </Button>
        <div>
          <h1>{user ? userName(user) : "Пользователь"}</h1>
          <p>ID {userId}</p>
        </div>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      {loading && !user ? (
        <Card className="empty-state">
          <Loader2 className="spin" size={24} />
          Загружаю...
        </Card>
      ) : null}

      {user ? (
        <>
          <Card className="admin-summary">
            <div className="admin-stats">
              <div className="admin-stat">
                <span>Подписок</span>
                <strong>{user.subscriptions}</strong>
                <small>{user.yummy_subscriptions ? `YummyAnime: ${user.yummy_subscriptions}` : "все с AnimeGO"}</small>
              </div>
              <div className="admin-stat">
                <span>Заходил</span>
                <strong className="admin-stat__text">{formatDay(user.last_active)}</strong>
                <small>
                  {user.active_days} дн. за {user.activity_days}
                </small>
              </div>
              <div className="admin-stat">
                <span>С нами с</span>
                <strong className="admin-stat__text">{formatDay(user.registered_at, timeZone)}</strong>
                <small>{user.activity_sources.length ? user.activity_sources.map((source) => (source === "miniapp" ? "мини-апп" : source === "bot" ? "бот" : source)).join(", ") : "—"}</small>
              </div>
            </div>
            <dl className="admin-user-facts">
              <dt>Любимые озвучки</dt>
              <dd>{describeVoiceovers(user.favorite_voiceovers, 5)}</dd>
              <dt>Часовой пояс</dt>
              <dd>{formatTimeZoneLabel(user.timezone)}</dd>
              <dt>Тихие часы</dt>
              <dd>{user.quiet_hours.enabled ? `${user.quiet_hours.start}–${user.quiet_hours.end}` : "выключены"}</dd>
            </dl>
          </Card>

          <section className="admin-subtitle">
            <h2>Подписки</h2>
          </section>
          {!user.subscriptions_list.length ? <Card className="empty-state">Подписок нет.</Card> : null}
          <div className="compact-list">
            {user.subscriptions_list.map((sub) => (
              <Card key={sub.id} className="subscription-row">
                <LazyImage className="subscription-row__poster" src={sub.poster_url || undefined} alt={sub.title} />
                <div className="subscription-row__main">
                  <ClampedTitle title={sub.title} />
                  <div className="subscription-row__meta">
                    <Badge tone="red">{sub.voiceover}</Badge>
                    {sub.source === "yummy" ? <Badge tone="muted">YummyAnime</Badge> : null}
                    <span>
                      {sub.last_episode || "Серия ?"} / {sub.total_episodes || "?"}
                    </span>
                  </div>
                  <p className="muted-copy admin-user-sub__hint">Последняя серия пришла: {formatDay(sub.last_episode_at, timeZone)}</p>
                </div>
                <div className="subscription-row__actions">
                  <Button size="icon" variant="ghost" aria-label="Открыть" onClick={() => openAnime(sub.link)}>
                    <ExternalLink size={18} />
                  </Button>
                  <Button
                    size={confirmDelete === sub.id ? "sm" : "icon"}
                    variant="danger"
                    disabled={pendingDelete !== null}
                    aria-label="Удалить подписку"
                    onClick={() => removeSubscription(sub.id)}
                  >
                    {pendingDelete === sub.id ? <Loader2 className="spin" size={18} /> : <Trash2 size={18} />}
                    {confirmDelete === sub.id ? "Удалить?" : null}
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
