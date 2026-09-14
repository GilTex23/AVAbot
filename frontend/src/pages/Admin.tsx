import { ArrowLeft, BarChart3, Check, ChevronRight, KeyRound, Link2, ListChecks, Loader2, Pencil, Plus, RefreshCw, Trash2, Users, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { AdminShikimori } from "./AdminShikimori";
import { AdminStats } from "./AdminStats";
import { AdminUsers } from "./AdminUsers";
import { describeAdminError } from "../lib/adminErrors";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Switch } from "../components/ui/switch";
import {
  ApiError,
  addAdminKey,
  deleteAdminKey,
  getAdminKeys,
  refreshAdminKeys,
  runSubscriptionsCheck,
  updateAdminKey,
} from "../services/api";
import type { ParserHealth, ScraperKey, ScraperKeyPatch, ScraperKeyStatus, ScraperKeysOverview, ScraperUsageDay } from "../lib/types";
import { hapticNotification, showTelegramBackButton } from "../lib/telegram";
import { cx } from "../lib/utils";

type AdminProps = {
  refreshKey: number;
  onBack: () => void;
};

type Tone = "green" | "red" | "muted" | "amber";

const numberFormat = new Intl.NumberFormat("ru-RU");

const statusMeta: Record<ScraperKeyStatus, { label: string; tone: Tone }> = {
  active: { label: "Работает", tone: "green" },
  low: { label: "Мало кредитов", tone: "amber" },
  exhausted: { label: "Исчерпан", tone: "red" },
  invalid: { label: "Недействителен", tone: "red" },
};

function formatNumber(value?: number | null) {
  return value === null || value === undefined ? "—" : numberFormat.format(value);
}

function plural(count: number, one: string, few: string, many: string) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) {
    return one;
  }
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) {
    return few;
  }
  return many;
}

function formatDayUsage(day: ScraperUsageDay) {
  return (
    `${formatNumber(day.success)} ${plural(day.success, "успешный", "успешных", "успешных")}, ` +
    `${formatNumber(day.failed)} ${plural(day.failed, "ошибка", "ошибки", "ошибок")}`
  );
}

function formatAgo(iso?: string | null) {
  if (!iso) {
    return "никогда";
  }
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) {
    return "только что";
  }
  if (minutes < 60) {
    return `${minutes} мин назад`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours} ч назад`;
  }
  return `${Math.round(hours / 24)} дн назад`;
}

function formatDate(iso: string, withYear = true) {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", ...(withYear ? { year: "numeric" } : {}) });
}

const describeError = describeAdminError;

function keyBadge(key: ScraperKey): { label: string; tone: Tone } {
  if (key.decrypt_error) {
    return { label: "Не расшифрован", tone: "red" };
  }
  if (!key.enabled) {
    return { label: "Выключен", tone: "muted" };
  }
  return statusMeta[key.status] ?? { label: key.status, tone: "muted" };
}

export function Admin({ refreshKey, onBack }: AdminProps) {
  const [view, setView] = useState<"main" | "stats" | "shikimori" | "users">("main");
  const openStats = useCallback(() => setView("stats"), []);
  const openShikimori = useCallback(() => setView("shikimori"), []);
  const openUsers = useCallback(() => setView("users"), []);
  const closeView = useCallback(() => setView("main"), []);

  if (view === "stats") {
    return <AdminStats refreshKey={refreshKey} onBack={closeView} />;
  }
  if (view === "shikimori") {
    return <AdminShikimori refreshKey={refreshKey} onBack={closeView} />;
  }
  if (view === "users") {
    return <AdminUsers refreshKey={refreshKey} onBack={closeView} />;
  }
  return <AdminMain refreshKey={refreshKey} onBack={onBack} onOpenStats={openStats} onOpenShikimori={openShikimori} onOpenUsers={openUsers} />;
}

type AdminMainProps = AdminProps & { onOpenStats: () => void; onOpenShikimori: () => void; onOpenUsers: () => void };

function AdminMain({ refreshKey, onBack, onOpenStats, onOpenShikimori, onOpenUsers }: AdminMainProps) {
  const [data, setData] = useState<ScraperKeysOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  useEffect(() => showTelegramBackButton(onBack), [onBack]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAdminKeys()
      .then((overview) => {
        if (!cancelled) {
          setData(overview);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(describeError(error, "Не удалось загрузить ключи. Попробуйте обновить страницу."));
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

  /** Выполняет действие админки; true, если оно прошло успешно */
  async function run(action: string, request: () => Promise<ScraperKeysOverview>, successText: string | null, errorText: string) {
    setBusy(action);
    setNotice(null);
    try {
      setData(await request());
      hapticNotification("success");
      if (successText) {
        setNotice(successText);
      }
      return true;
    } catch (error) {
      hapticNotification("error");
      setNotice(describeError(error, errorText));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function startSubscriptionsCheck() {
    setBusy("check");
    setNotice(null);
    try {
      await runSubscriptionsCheck();
      setData((current) => (current ? { ...current, subscriptions_check_running: true } : current));
      hapticNotification("success");
      setNotice("Проверка подписок запущена — итог придёт в Telegram.");
    } catch (error) {
      hapticNotification("error");
      setNotice(describeError(error, "Не удалось запустить проверку подписок."));
    } finally {
      setBusy(null);
    }
  }

  const summary = data?.summary;

  return (
    <div className="page-stack">
      <section className="admin-title">
        <Button size="icon" variant="ghost" aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} />
        </Button>
        <div>
          <h1>Админка</h1>
          <p>Ключи ScraperAPI и проверка подписок</p>
        </div>
      </section>

      <button type="button" className="card settings-card settings-link" onClick={onOpenStats}>
        <span className="settings-card__head">
          <BarChart3 size={22} />
          <span className="settings-link__text">
            <span className="settings-link__title">Статистика</span>
            <span className="settings-link__caption">Запросы и ключи, бот, база данных и сервер — с графиками</span>
          </span>
        </span>
        <ChevronRight size={20} />
      </button>

      <button type="button" className="card settings-card settings-link" onClick={onOpenUsers}>
        <span className="settings-card__head">
          <Users size={22} />
          <span className="settings-link__text">
            <span className="settings-link__title">Пользователи</span>
            <span className="settings-link__caption">Кто пользуется ботом, настройки и подписки каждого</span>
          </span>
        </span>
        <ChevronRight size={20} />
      </button>

      <button type="button" className="card settings-card settings-link" onClick={onOpenShikimori}>
        <span className="settings-card__head">
          <Link2 size={22} />
          <span className="settings-link__text">
            <span className="settings-link__title">Shikimori</span>
            <span className="settings-link__caption">Сопоставление тайтлов: не найденные, неоднозначные, ручной выбор</span>
          </span>
        </span>
        <ChevronRight size={20} />
      </button>

      {notice ? <div className="notice">{notice}</div> : null}

      {loading && !data ? (
        <Card className="empty-state">
          <Loader2 className="spin" size={24} />
          Загружаю ключи...
        </Card>
      ) : null}

      {data && summary ? (
        <>
          <Card className="admin-summary">
            <div className="admin-stats">
              <div className="admin-stat">
                <span>Осталось кредитов</span>
                <strong>{formatNumber(summary.remaining)}</strong>
                <small>из {formatNumber(summary.limit)}</small>
              </div>
              <div className="admin-stat">
                <span>Хватит примерно на</span>
                <strong>{summary.days_left === null ? "—" : `${formatNumber(Math.floor(summary.days_left))} дн.`}</strong>
                <small>
                  {summary.avg_daily === null
                    ? "мало статистики"
                    : `~${formatNumber(Math.round(summary.avg_daily))} ${plural(Math.round(summary.avg_daily), "запрос", "запроса", "запросов")} в день`}
                </small>
              </div>
              <div className="admin-stat">
                <span>Рабочих ключей</span>
                <strong className={cx(summary.usable_keys === 0 && "admin-stat__danger")}>{summary.usable_keys}</strong>
                <small>из {summary.total_keys}</small>
              </div>
            </div>

            <UsageChart usage={data.usage} />

            <div className="admin-actions">
              <Button disabled={busy !== null} onClick={() => run("refresh-all", () => refreshAdminKeys(), "Данные ключей обновлены.", "Не удалось обновить ключи.")}>
                {busy === "refresh-all" ? <Loader2 className="spin" size={17} /> : <RefreshCw size={17} />}
                Обновить ключи
              </Button>
              <Button disabled={busy !== null || data.subscriptions_check_running} onClick={startSubscriptionsCheck}>
                {busy === "check" || data.subscriptions_check_running ? <Loader2 className="spin" size={17} /> : <ListChecks size={17} />}
                {data.subscriptions_check_running ? "Проверка идёт" : "Проверить подписки"}
              </Button>
            </div>
          </Card>

          {data.parser_health ? <ParserHealthCard health={data.parser_health} /> : null}

          <section className="admin-subtitle">
            <h2>Ключи</h2>
            {!adding ? (
              <Button size="sm" variant="primary" onClick={() => setAdding(true)}>
                <Plus size={16} />
                Добавить
              </Button>
            ) : null}
          </section>

          {adding ? (
            <AddKeyForm
              busy={busy === "add"}
              disabled={busy !== null}
              onCancel={() => setAdding(false)}
              onSubmit={async (key) => {
                const ok = await run("add", () => addAdminKey(key), `Ключ «${key.name}» добавлен.`, "Не удалось добавить ключ.");
                if (ok) {
                  setAdding(false);
                }
              }}
            />
          ) : null}

          <div className="compact-list">
            {data.keys.map((key) => (
              <KeyCard
                key={key.id}
                item={key}
                busy={busy}
                onRefresh={() => run(`refresh-${key.id}`, () => refreshAdminKeys(key.id), null, "Не удалось проверить ключ.")}
                onUpdate={(patch, successText) => run(`update-${key.id}`, () => updateAdminKey(key.id, patch), successText, "Не удалось сохранить ключ.")}
                onDelete={() => run(`delete-${key.id}`, () => deleteAdminKey(key.id), `Ключ «${key.name}» удалён.`, "Не удалось удалить ключ.")}
              />
            ))}
          </div>

          {data.keys.length === 0 ? (
            <Card className="empty-state">
              <KeyRound size={24} />
              Ключей нет — парсинг AnimeGO не работает. Добавьте хотя бы один ключ.
            </Card>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

function ParserHealthCard({ health }: { health: ParserHealth }) {
  const checked = Boolean(health.last_attempt_at);
  // Незнакомый часовой пояс — не сбой: уведомления работают, просто время с этой загрузки не используется
  const failing = health.consecutive_failures > 0;
  const badge: { label: string; tone: Tone } = !checked
    ? { label: "Ещё не проверялся", tone: "muted" }
    : failing
      ? { label: health.consecutive_failures >= health.failure_threshold ? "Не работает" : "Сбой", tone: "red" }
      : health.problems.length
        ? { label: "Внимание", tone: "amber" }
        : { label: "Работает", tone: "green" };

  return (
    <Card className="key-card">
      <div className="key-card__head">
        <div className="key-card__title">
          <h2>Парсер AnimeGO</h2>
          <p>Главная страница: лента новых серий и расписание</p>
        </div>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>

      {checked ? (
        <dl className="key-card__facts">
          <div>
            <dt>Успешная загрузка</dt>
            <dd>{formatAgo(health.last_success_at)}</dd>
          </div>
          <div>
            <dt>В ленте</dt>
            <dd>{formatNumber(health.updates_count)}</dd>
          </div>
          <div>
            <dt>В расписании</dt>
            <dd>
              {formatNumber(health.schedule_count)} (со временем {formatNumber(health.timed_schedule_count)})
            </dd>
          </div>
          <div>
            <dt>Пояс прокси</dt>
            <dd>{health.timezone || "—"}</dd>
          </div>
        </dl>
      ) : (
        <p className="muted-copy">Данные появятся после первой проверки обновлений (раз в 20 минут).</p>
      )}

      {health.problems.length ? (
        <p className="key-card__error">
          <span>
            {failing
              ? `Проблема в ${health.consecutive_failures} ${plural(health.consecutive_failures, "загрузке", "загрузках", "загрузках")} подряд · админам пишем после ${health.failure_threshold}`
              : "Время с последней загрузки не использовано · админам уже написали"}
          </span>
          {health.problems.join(". ")}
        </p>
      ) : null}
    </Card>
  );
}

function UsageChart({ usage }: { usage: ScraperUsageDay[] }) {
  const [selected, setSelected] = useState(usage.length - 1);
  const max = Math.max(1, ...usage.map((day) => day.success + day.failed));
  const selectedDay = usage[Math.min(selected, usage.length - 1)];

  if (!usage.length) {
    return null;
  }

  return (
    <div className="usage-chart">
      <div className="usage-chart__head">
        <span>Запросы за {usage.length} дн.</span>
        <span className="usage-chart__legend">
          <i className="usage-chart__dot usage-chart__dot--success" />
          успешные
          <i className="usage-chart__dot usage-chart__dot--failed" />
          ошибки
        </span>
      </div>
      <div className="usage-chart__bars">
        {usage.map((day, index) => {
          const total = day.success + day.failed;
          return (
            <button
              key={day.day}
              type="button"
              className={cx("usage-chart__col", index === selected && "usage-chart__col--selected")}
              aria-label={`${formatDate(day.day, false)}: ${formatDayUsage(day)}`}
              onClick={() => setSelected(index)}
            >
              <span className="usage-chart__stack" style={{ height: total ? `max(3px, ${(total / max) * 100}%)` : 0 }}>
                <span className="usage-chart__failed" style={{ flexGrow: day.failed }} />
                <span className="usage-chart__success" style={{ flexGrow: day.success }} />
              </span>
            </button>
          );
        })}
      </div>
      {selectedDay ? (
        <p className="usage-chart__caption">
          {selected === usage.length - 1 ? "Сегодня" : formatDate(selectedDay.day, false)}: {formatDayUsage(selectedDay)}
        </p>
      ) : null}
    </div>
  );
}

type AddKeyFormProps = {
  busy: boolean;
  disabled: boolean;
  onCancel: () => void;
  onSubmit: (key: { name: string; email: string; key: string }) => void;
};

function AddKeyForm({ busy, disabled, onCancel, onSubmit }: AddKeyFormProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [apiKey, setApiKey] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit({ name: name.trim(), email: email.trim(), key: apiKey.trim() });
  }

  return (
    <Card className="settings-card settings-card--column">
      <form className="admin-form" onSubmit={submit}>
        <h2>Новый ключ</h2>
        <label className="field-stack">
          <span>Название</span>
          <Input value={name} maxLength={64} placeholder="Например, V.1.V" onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="field-stack">
          <span>Почта аккаунта ScraperAPI</span>
          <Input type="email" value={email} maxLength={254} placeholder="name@mail.ru" onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label className="field-stack">
          <span>API-ключ</span>
          <Input
            type="password"
            value={apiKey}
            autoComplete="off"
            spellCheck={false}
            placeholder="Ключ из дашборда ScraperAPI"
            onChange={(event) => setApiKey(event.target.value)}
          />
        </label>
        <p className="muted-copy">Перед сохранением ключ проверяется через ScraperAPI. В базе он хранится зашифрованным.</p>
        <div className="admin-form__buttons">
          <Button type="button" variant="ghost" disabled={busy} onClick={onCancel}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={disabled || !name.trim() || !apiKey.trim()}>
            {busy ? <Loader2 className="spin" size={17} /> : <Plus size={17} />}
            {busy ? "Проверяю" : "Добавить"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

type KeyCardProps = {
  item: ScraperKey;
  busy: string | null;
  onRefresh: () => void;
  onUpdate: (patch: ScraperKeyPatch, successText: string | null) => Promise<boolean>;
  onDelete: () => void;
};

function KeyCard({ item, busy, onRefresh, onUpdate, onDelete }: KeyCardProps) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [name, setName] = useState(item.name);
  const [email, setEmail] = useState(item.email || "");

  const badge = keyBadge(item);
  const used = item.request_count ?? 0;
  const limit = item.request_limit ?? 0;
  const usedPercent = limit ? Math.min(100, (used / limit) * 100) : 0;
  const meterTone = !item.enabled ? "muted" : item.status === "active" ? "green" : item.status === "low" ? "amber" : "red";
  const anyBusy = busy !== null;

  function startEditing() {
    setName(item.name);
    setEmail(item.email || "");
    setConfirmDelete(false);
    setEditing(true);
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    const ok = await onUpdate({ name: name.trim(), email: email.trim() }, "Ключ сохранён.");
    if (ok) {
      setEditing(false);
    }
  }

  return (
    <Card className={cx("key-card", !item.enabled && "key-card--disabled")}>
      <div className="key-card__head">
        <div className="key-card__title">
          <h2>{item.name}</h2>
          <p>{item.email || "почта не указана"}</p>
        </div>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>

      <code className="key-card__mask">{item.masked_key}</code>

      {limit ? (
        <div className="key-card__usage">
          <div className="key-meter" role="meter" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={used} aria-label="Израсходовано кредитов">
            <span className={`key-meter__fill key-meter__fill--${meterTone}`} style={{ width: `${usedPercent}%` }} />
          </div>
          <div className="key-card__numbers">
            <span>
              Израсходовано {formatNumber(used)} из {formatNumber(limit)}
            </span>
            <strong>осталось {formatNumber(item.remaining)}</strong>
          </div>
        </div>
      ) : (
        <p className="muted-copy">Данных о лимите пока нет — нажмите «Обновить».</p>
      )}

      <dl className="key-card__facts">
        <div>
          <dt>Проверен</dt>
          <dd>{formatAgo(item.last_checked_at)}</dd>
        </div>
        <div>
          <dt>Успешный запрос</dt>
          <dd>{formatAgo(item.last_used_at)}</dd>
        </div>
        {item.subscription_date ? (
          <div>
            <dt>Подписка с</dt>
            <dd>{formatDate(item.subscription_date)}</dd>
          </div>
        ) : null}
      </dl>

      {item.last_error ? (
        <p className="key-card__error">
          <span>Последняя ошибка · {formatAgo(item.last_error_at)}</span>
          {item.last_error}
        </p>
      ) : null}

      {editing ? (
        <form className="admin-form" onSubmit={saveEdit}>
          <label className="field-stack">
            <span>Название</span>
            <Input value={name} maxLength={64} onChange={(event) => setName(event.target.value)} />
          </label>
          <label className="field-stack">
            <span>Почта</span>
            <Input type="email" value={email} maxLength={254} placeholder="name@mail.ru" onChange={(event) => setEmail(event.target.value)} />
          </label>
          <div className="admin-form__buttons">
            <Button type="button" variant="ghost" disabled={anyBusy} onClick={() => setEditing(false)}>
              <X size={17} />
              Отмена
            </Button>
            <Button type="submit" variant="primary" disabled={anyBusy || !name.trim()}>
              {busy === `update-${item.id}` ? <Loader2 className="spin" size={17} /> : <Check size={17} />}
              Сохранить
            </Button>
          </div>
        </form>
      ) : confirmDelete ? (
        <div className="key-card__confirm">
          <span>Удалить ключ «{item.name}»? Его статистика тоже удалится.</span>
          <div className="admin-form__buttons">
            <Button variant="ghost" disabled={anyBusy} onClick={() => setConfirmDelete(false)}>
              Отмена
            </Button>
            <Button variant="danger" disabled={anyBusy} onClick={onDelete}>
              {busy === `delete-${item.id}` ? <Loader2 className="spin" size={17} /> : <Trash2 size={17} />}
              Удалить
            </Button>
          </div>
        </div>
      ) : (
        <div className="key-card__actions">
          <Switch
            checked={item.enabled}
            label="В ротации"
            onChange={(enabled) => {
              if (!anyBusy) {
                onUpdate({ enabled }, enabled ? `Ключ «${item.name}» включён.` : `Ключ «${item.name}» выключен.`);
              }
            }}
          />
          <div className="key-card__buttons">
            <Button size="icon" variant="ghost" aria-label="Проверить ключ" disabled={anyBusy} onClick={onRefresh}>
              {busy === `refresh-${item.id}` ? <Loader2 className="spin" size={18} /> : <RefreshCw size={18} />}
            </Button>
            <Button size="icon" variant="ghost" aria-label="Изменить" disabled={anyBusy} onClick={startEditing}>
              <Pencil size={18} />
            </Button>
            <Button size="icon" variant="danger" aria-label="Удалить" disabled={anyBusy} onClick={() => setConfirmDelete(true)}>
              <Trash2 size={18} />
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
