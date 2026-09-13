import { ArrowLeft, Check, ExternalLink, Link2, Loader2, RefreshCw, SearchX, X } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { describeAdminError } from "../lib/adminErrors";
import { hapticNotification, showTelegramBackButton } from "../lib/telegram";
import { useTimeZone } from "../lib/timezones";
import type { ShikimoriCandidate, ShikimoriOverview, ShikimoriTitle, ShikimoriTitleStatus } from "../lib/types";
import { openAnime } from "../lib/utils";
import { getAdminShikimori, runShikimoriSync, updateShikimoriMatch } from "../services/api";

type AdminShikimoriProps = {
  refreshKey: number;
  onBack: () => void;
};

type Tone = "green" | "red" | "muted" | "amber";

const statusMeta: Record<ShikimoriTitleStatus, { label: string; tone: Tone }> = {
  matched: { label: "Найден", tone: "green" },
  manual: { label: "Выбран вручную", tone: "green" },
  ambiguous: { label: "Неоднозначно", tone: "amber" },
  not_found: { label: "Не найден", tone: "amber" },
  error: { label: "Ошибка", tone: "red" },
  pending: { label: "Ещё не искали", tone: "muted" },
  absent: { label: "Нет на Shikimori", tone: "muted" },
};

const ATTENTION: ShikimoriTitleStatus[] = ["ambiguous", "not_found", "error", "pending"];

const kindLabels: Record<string, string> = {
  tv: "ТВ",
  movie: "фильм",
  ova: "OVA",
  ona: "ONA",
  special: "спешл",
  tv_special: "ТВ-спешл",
  music: "клип",
  pv: "PV",
  cm: "реклама",
};

function describeCandidate(candidate: Pick<ShikimoriCandidate, "kind" | "year" | "episodes">) {
  return [candidate.kind ? kindLabels[candidate.kind] ?? candidate.kind : null, candidate.year, candidate.episodes ? `${candidate.episodes} сер.` : null]
    .filter(Boolean)
    .join(" · ");
}

export function AdminShikimori({ refreshKey, onBack }: AdminShikimoriProps) {
  const [data, setData] = useState<ShikimoriOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [onlyAttention, setOnlyAttention] = useState(true);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => showTelegramBackButton(onBack), [onBack]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getAdminShikimori()
      .then((overview) => {
        if (!cancelled) {
          setData(overview);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setNotice(describeAdminError(error, "Не удалось загрузить тайтлы. Попробуйте ещё раз."));
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
  }, [refreshKey, reloadKey]);

  async function update(action: string, animeId: number, payload: Parameters<typeof updateShikimoriMatch>[1], successText: string) {
    setBusy(`${action}:${animeId}`);
    setNotice(null);
    try {
      setData(await updateShikimoriMatch(animeId, payload));
      hapticNotification("success");
      setNotice(successText);
      return true;
    } catch (error) {
      hapticNotification("error");
      setNotice(describeAdminError(error, "Не удалось сохранить. Попробуйте ещё раз."));
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function startSync() {
    setBusy("sync");
    setNotice(null);
    try {
      await runShikimoriSync();
      setData((current) => (current ? { ...current, running: true } : current));
      hapticNotification("success");
      setNotice("Синхронизация запущена: несопоставленные тайтлы ищутся заново. Обновите экран через минуту.");
    } catch (error) {
      hapticNotification("error");
      setNotice(describeAdminError(error, "Не удалось запустить синхронизацию."));
    } finally {
      setBusy(null);
    }
  }

  const titles = data?.titles ?? [];
  const attentionCount = titles.filter((title) => ATTENTION.includes(title.status)).length;
  const visible = onlyAttention ? titles.filter((title) => ATTENTION.includes(title.status)) : titles;

  return (
    <div className="page-stack">
      <section className="admin-title">
        <Button size="icon" variant="ghost" aria-label="Назад" onClick={onBack}>
          <ArrowLeft size={20} />
        </Button>
        <div>
          <h1>Shikimori</h1>
          <p>Сопоставление тайтлов с подписками</p>
        </div>
      </section>

      <Card className="settings-card settings-card--column">
        <p className="muted-copy">
          С Shikimori бот берёт число серий, статус и время выхода оригинала — без запросов к AnimeGO. Если тайтл не найден или найден
          неуверенно, бот работает только по AnimeGO. Здесь можно выбрать тайтл вручную или отметить, что его на Shikimori нет.
        </p>
        {data && !data.enabled ? <div className="notice">Shikimori выключен: SHIKIMORI_ENABLED=false.</div> : null}
        {data ? (
          <div className="shiki-summary">
            {(Object.keys(statusMeta) as ShikimoriTitleStatus[])
              .filter((status) => data.summary[status])
              .map((status) => (
                <Badge key={status} tone={statusMeta[status].tone}>
                  {statusMeta[status].label}: {data.summary[status]}
                </Badge>
              ))}
          </div>
        ) : null}
        <div className="admin-actions">
          <Button variant="secondary" size="sm" disabled={loading} onClick={() => setReloadKey((value) => value + 1)}>
            {loading ? <Loader2 className="spin" size={16} /> : <RefreshCw size={16} />}
            Обновить
          </Button>
          <Button variant="primary" size="sm" disabled={!data?.enabled || data.running || busy === "sync"} onClick={startSync}>
            {busy === "sync" || data?.running ? <Loader2 className="spin" size={16} /> : <SearchX size={16} />}
            {data?.running ? "Идёт синхронизация" : "Искать заново"}
          </Button>
        </div>
      </Card>

      {notice ? <div className="notice">{notice}</div> : null}

      {data ? (
        <div className="chip-row" aria-label="Фильтр тайтлов">
          <button type="button" className={onlyAttention ? "chip chip--active" : "chip"} onClick={() => setOnlyAttention(true)}>
            Требуют внимания<span className="chip__count">{attentionCount}</span>
          </button>
          <button type="button" className={!onlyAttention ? "chip chip--active" : "chip"} onClick={() => setOnlyAttention(false)}>
            Все<span className="chip__count">{titles.length}</span>
          </button>
        </div>
      ) : null}

      {loading && !data ? (
        <Card className="empty-state">
          <Loader2 className="spin" size={24} />
          Загружаю тайтлы...
        </Card>
      ) : null}

      {data && !visible.length ? (
        <Card className="empty-state">{onlyAttention ? "Все тайтлы с подписками сопоставлены или отмечены." : "Подписок пока нет."}</Card>
      ) : null}

      <div className="compact-list">
        {visible.map((title) => (
          <ShikimoriTitleCard
            key={title.id}
            title={title}
            busy={busy}
            enabled={Boolean(data?.enabled)}
            onPick={(value, text) => update("pick", title.id, { shikimori: value }, text)}
            onAbsent={() => update("absent", title.id, { absent: true }, `«${title.title}»: отмечено, что на Shikimori его нет.`)}
            onRecheck={() => update("recheck", title.id, { recheck: true }, `«${title.title}»: поиск выполнен заново.`)}
          />
        ))}
      </div>
    </div>
  );
}

type ShikimoriTitleCardProps = {
  title: ShikimoriTitle;
  busy: string | null;
  enabled: boolean;
  onPick: (value: string | number, successText: string) => Promise<boolean>;
  onAbsent: () => void;
  onRecheck: () => void;
};

function ShikimoriTitleCard({ title, busy, enabled, onPick, onAbsent, onRecheck }: ShikimoriTitleCardProps) {
  const timeZone = useTimeZone();
  const needsAttention = ATTENTION.includes(title.status);
  const [editing, setEditing] = useState(false);
  const [link, setLink] = useState("");
  const meta = statusMeta[title.status] ?? { label: title.status, tone: "muted" as Tone };
  const animego = [title.animego.kind, title.animego.year, title.animego.episodes ? `${title.animego.episodes} сер.` : null, title.animego.english_title]
    .filter(Boolean)
    .join(" · ");
  const isBusy = (action: string) => busy === `${action}:${title.id}`;
  const showTools = needsAttention || editing;
  const otherCandidates = title.candidates.filter((candidate) => candidate.id !== title.shikimori?.id);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (link.trim() && (await onPick(link.trim(), `«${title.title}»: тайтл Shikimori сохранён.`))) {
      setLink("");
      setEditing(false);
    }
  }

  return (
    <Card className="shiki-title">
      <div className="shiki-title__head">
        <div>
          <h2>{title.title}</h2>
          <p className="muted-copy">
            {animego || "Страницу тайтла ещё не открывали — ищем только по названию"} · подписок: {title.subscriptions}
          </p>
        </div>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>

      {title.shikimori ? (
        <div className="shiki-title__match">
          <button type="button" className="shiki-link" onClick={() => title.shikimori?.url && openAnime(title.shikimori.url)}>
            <Link2 size={15} />
            {title.shikimori.russian || title.shikimori.name}
          </button>
          <span>
            {describeCandidate({ kind: title.shikimori.kind, year: title.shikimori.year, episodes: title.shikimori.episodes })}
            {title.shikimori.episodes_aired !== null && title.shikimori.status === "ongoing" ? ` · вышло ${title.shikimori.episodes_aired}` : ""}
          </span>
          {title.shikimori.next_episode_at ? (
            <span>
              Следующая серия:{" "}
              {new Date(title.shikimori.next_episode_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone })}
            </span>
          ) : null}
        </div>
      ) : null}

      {title.status === "error" && title.error ? <p className="muted-copy">Shikimori ответил ошибкой: {title.error}</p> : null}

      {showTools && otherCandidates.length ? (
        <div className="shiki-candidates">
          <span className="muted-copy">{title.shikimori ? "Другие кандидаты:" : "Похожие тайтлы на Shikimori:"}</span>
          {otherCandidates.map((candidate) => (
              <div key={candidate.id} className="shiki-candidate">
                <button type="button" className="shiki-link" onClick={() => candidate.url && openAnime(candidate.url)}>
                  <ExternalLink size={14} />
                  {candidate.russian || candidate.name}
                </button>
                <span>{describeCandidate(candidate)}</span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={!enabled || Boolean(busy)}
                  onClick={() => onPick(candidate.id, `«${title.title}»: выбран «${candidate.russian || candidate.name}».`).then((ok) => ok && setEditing(false))}
                >
                  {isBusy("pick") ? <Loader2 className="spin" size={15} /> : <Check size={15} />}
                  Это он
                </Button>
              </div>
            ))}
        </div>
      ) : null}

      {showTools ? (
        <form className="shiki-form" onSubmit={submit}>
          <Input placeholder="Ссылка или id на Shikimori" value={link} onChange={(event) => setLink(event.target.value)} />
          <Button type="submit" size="sm" variant="primary" disabled={!enabled || !link.trim() || Boolean(busy)}>
            {isBusy("pick") ? <Loader2 className="spin" size={15} /> : <Check size={15} />}
            Сохранить
          </Button>
        </form>
      ) : null}

      <div className="admin-actions">
        <Button size="sm" variant="ghost" onClick={() => openAnime(title.url)}>
          <ExternalLink size={15} />
          AnimeGO
        </Button>
        {!showTools ? (
          <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
            Изменить
          </Button>
        ) : null}
        {showTools && title.status !== "absent" ? (
          <Button size="sm" variant="ghost" disabled={Boolean(busy)} onClick={onAbsent}>
            {isBusy("absent") ? <Loader2 className="spin" size={15} /> : <X size={15} />}
            Нет на Shikimori
          </Button>
        ) : null}
        {showTools ? (
          <Button size="sm" variant="ghost" disabled={!enabled || Boolean(busy)} onClick={onRecheck}>
            {isBusy("recheck") ? <Loader2 className="spin" size={15} /> : <RefreshCw size={15} />}
            Искать заново
          </Button>
        ) : null}
        {editing ? (
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>
            Отмена
          </Button>
        ) : null}
      </div>
    </Card>
  );
}
