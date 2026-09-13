import { Check, ChevronRight, Loader2, Save, Search, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { errorText, getVoiceovers, saveFavoriteVoiceovers, saveQuietHours, saveTimeZone } from "../services/api";
import type { UserProfile, VoiceoverCatalogItem } from "../lib/types";
import { hapticNotification } from "../lib/telegram";
import { describeVoiceovers } from "../lib/utils";
import { DEFAULT_TIME_ZONE, formatTimeZoneLabel, getTimeZones } from "../lib/timezones";

type SettingsProps = {
  user?: UserProfile | null;
  onUserUpdated: (user: UserProfile | null) => void;
  onOpenAdmin: () => void;
};

export function Settings({ user, onUserUpdated, onOpenAdmin }: SettingsProps) {
  const [favorites, setFavorites] = useState<string[]>(user?.favorite_voiceovers ?? []);
  const [quietMode, setQuietMode] = useState(user?.quiet_hours_enabled || false);
  const [quietStart, setQuietStart] = useState(user?.quiet_hours_start || "23:00");
  const [quietEnd, setQuietEnd] = useState(user?.quiet_hours_end || "09:00");
  const [timezone, setTimezone] = useState(user?.quiet_timezone || DEFAULT_TIME_ZONE);
  const [savingVoiceover, setSavingVoiceover] = useState(false);
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [savingQuiet, setSavingQuiet] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  // Сохранённый пояс может не входить в список браузера (например, устаревшее имя) — показываем и его
  const timeZones = useMemo(() => getTimeZones(user?.quiet_timezone), [user?.quiet_timezone]);
  const savedTimezone = user?.quiet_timezone || DEFAULT_TIME_ZONE;

  useEffect(() => {
    setFavorites(user?.favorite_voiceovers ?? []);
    setQuietMode(user?.quiet_hours_enabled || false);
    setQuietStart(user?.quiet_hours_start || "23:00");
    setQuietEnd(user?.quiet_hours_end || "09:00");
    setTimezone(user?.quiet_timezone || DEFAULT_TIME_ZONE);
  }, [user]);

  async function saveUserTimezone() {
    setSavingTimezone(true);
    setNotice(null);
    try {
      const result = await saveTimeZone(timezone);
      onUserUpdated(user ? { ...user, quiet_timezone: result.quiet_timezone } : null);
      hapticNotification("success");
      setNotice("Часовой пояс сохранён.");
    } catch {
      hapticNotification("error");
      setNotice("Не удалось сохранить часовой пояс.");
    } finally {
      setSavingTimezone(false);
    }
  }

  async function saveFavorites() {
    setSavingVoiceover(true);
    setNotice(null);
    try {
      const result = await saveFavoriteVoiceovers(favorites);
      onUserUpdated(user ? { ...user, favorite_voiceovers: result.favorite_voiceovers } : null);
      hapticNotification("success");
      setNotice("Любимые озвучки сохранены.");
    } catch (error) {
      hapticNotification("error");
      setNotice(errorText(error, "Не удалось сохранить озвучки."));
    } finally {
      setSavingVoiceover(false);
    }
  }

  async function saveQuietSettings() {
    setSavingQuiet(true);
    setNotice(null);
    try {
      const result = await saveQuietHours({
        enabled: quietMode,
        start: quietStart,
        end: quietEnd,
      });
      onUserUpdated(
        user
          ? {
              ...user,
              quiet_hours_enabled: result.quiet_hours_enabled,
              quiet_hours_start: result.quiet_hours_start,
              quiet_hours_end: result.quiet_hours_end,
            }
          : null,
      );
      hapticNotification("success");
      setNotice("Тихие часы сохранены.");
    } catch {
      hapticNotification("error");
      setNotice("Не удалось сохранить тихие часы.");
    } finally {
      setSavingQuiet(false);
    }
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Настройки</h1>
        <p>Профиль Telegram, озвучка, часовой пояс и тихие часы</p>
      </section>

      {notice ? <div className="notice">{notice}</div> : null}

      <Card className="settings-card">
        <div className="settings-card__head">
          {user?.photo_url ? <img className="settings-card__avatar" src={user.photo_url} alt={user?.username || "Telegram user"} /> : <SlidersHorizontal size={22} />}
          <div>
            <h2>{user?.username ? `@${user.username}` : "Telegram профиль"}</h2>
            <p>ID {user?.id || "не определён"}</p>
          </div>
        </div>
        <Badge tone="green">{user?.subscriptions_count || 0} подписок</Badge>
      </Card>

      {user?.is_admin ? (
        <button type="button" className="card settings-card settings-link" onClick={onOpenAdmin}>
          <span className="settings-card__head">
            <ShieldCheck size={22} />
            <span className="settings-link__text">
              <span className="settings-link__title">Администрирование</span>
              <span className="settings-link__caption">Ключи ScraperAPI и проверка подписок</span>
            </span>
          </span>
          <ChevronRight size={20} />
        </button>
      ) : null}

      <Card className="settings-card settings-card--column">
        <h2>Любимые озвучки</h2>
        <FavoriteVoiceoversPicker selected={favorites} saved={user?.favorite_voiceovers ?? []} onChange={setFavorites} />
        <Button variant="primary" disabled={savingVoiceover} onClick={saveFavorites}>
          {savingVoiceover ? <Loader2 className="spin" size={17} /> : sameNames(user?.favorite_voiceovers ?? [], favorites) ? <Check size={17} /> : <Save size={17} />}
          {savingVoiceover ? "Сохраняю" : "Сохранить озвучки"}
        </Button>
      </Card>

      <Card className="settings-card settings-card--column">
        <h2>Часовой пояс</h2>
        <label className="field-stack">
          <span>Время в расписании, прогнозах серий и тихих часах</span>
          <select className="input select" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
            {timeZones.map((item) => (
              <option key={item} value={item}>
                {formatTimeZoneLabel(item)}
              </option>
            ))}
          </select>
        </label>
        <p className="muted-copy">По умолчанию — Москва (Europe/Moscow, UTC+3).</p>
        <Button variant="primary" disabled={savingTimezone} onClick={saveUserTimezone}>
          {savingTimezone ? <Loader2 className="spin" size={17} /> : savedTimezone === timezone ? <Check size={17} /> : <Save size={17} />}
          {savingTimezone ? "Сохраняю" : "Сохранить часовой пояс"}
        </Button>
      </Card>

      <Card className="settings-card settings-card--column">
        <Switch checked={quietMode} onChange={setQuietMode} label="Тихие часы" />
        <div className="settings-grid">
          <label>
            <span>Начало</span>
            <input className="input" type="time" value={quietStart} onChange={(event) => setQuietStart(event.target.value)} />
          </label>
          <label>
            <span>Конец</span>
            <input className="input" type="time" value={quietEnd} onChange={(event) => setQuietEnd(event.target.value)} />
          </label>
        </div>
        <p className="muted-copy">Время тихих часов — по вашему часовому поясу: {formatTimeZoneLabel(savedTimezone)}.</p>
        <Button variant="primary" disabled={savingQuiet} onClick={saveQuietSettings}>
          {savingQuiet ? <Loader2 className="spin" size={17} /> : <Save size={17} />}
          {savingQuiet ? "Сохраняю" : "Сохранить тихие часы"}
        </Button>
      </Card>
    </div>
  );
}

const COLLAPSED_COUNT = 12;
const MAX_FAVORITES = 20;

function sameNames(left: string[], right: string[]) {
  return left.length === right.length && left.every((name) => right.includes(name));
}

type FavoriteVoiceoversPickerProps = {
  selected: string[];
  saved: string[];
  onChange: Dispatch<SetStateAction<string[]>>;
};

/** Отметки озвучек из справочника: сохранённые любимые сверху, дальше — самые активные */
function FavoriteVoiceoversPicker({ selected, saved, onChange }: FavoriteVoiceoversPickerProps) {
  const [catalog, setCatalog] = useState<VoiceoverCatalogItem[] | null>(null);
  const [popularDays, setPopularDays] = useState(60);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getVoiceovers()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data.items);
          setPopularDays(data.popular_days);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Порядок зависит только от сохранённых любимых, чтобы кнопки не прыгали при нажатии
  const ordered = useMemo(() => {
    if (!catalog) {
      return [];
    }
    const pinned = saved
      .map((name) => catalog.find((item) => item.name === name))
      .filter((item): item is VoiceoverCatalogItem => Boolean(item));
    return [...pinned, ...catalog.filter((item) => !saved.includes(item.name))];
  }, [catalog, saved]);

  const needle = query.trim().toLowerCase();
  const matching = needle ? ordered.filter((item) => item.name.toLowerCase().includes(needle)) : ordered;
  const visible = needle || expanded ? matching : matching.slice(0, COLLAPSED_COUNT);

  function toggle(name: string) {
    if (!selected.includes(name) && selected.length >= MAX_FAVORITES) {
      hapticNotification("warning");
      return;
    }
    // От текущего состояния, а не от selected из замыкания: быстрые нажатия подряд не затирают друг друга
    onChange((current) => {
      if (current.includes(name)) {
        return current.filter((item) => item !== name);
      }
      return current.length < MAX_FAVORITES ? [...current, name] : current;
    });
  }

  if (failed) {
    return <p className="muted-copy">Не удалось загрузить список озвучек.</p>;
  }
  if (!catalog) {
    return (
      <p className="muted-copy">
        <Loader2 className="spin" size={15} /> Загружаю озвучки...
      </p>
    );
  }
  if (!catalog.length) {
    return <p className="muted-copy">Список озвучек появится после первой проверки ленты.</p>;
  }

  return (
    <div className="voiceover-picker">
      <div className="voiceover-picker__summary">
        <Badge tone={selected.length ? "red" : "muted"}>{describeVoiceovers(selected, 2)}</Badge>
        {selected.length ? (
          <button type="button" className="voiceover-picker__more" onClick={() => onChange([])}>
            Сбросить
          </button>
        ) : null}
      </div>
      <p className="muted-copy">
        «Свежие серии» по умолчанию покажут только отмеченные озвучки, а если ничего не отмечено — все. Сверху — самые активные за {popularDays} дней.
      </p>
      {catalog.length > COLLAPSED_COUNT ? (
        <label className="search-field">
          <Search size={17} />
          <input className="input" type="search" placeholder="Найти озвучку" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
      ) : null}
      <div className="chip-row chip-row--wrap">
        {visible.map((item) => (
          <button key={item.id} className={selected.includes(item.name) ? "chip chip--active" : "chip"} type="button" onClick={() => toggle(item.name)}>
            {item.name}
          </button>
        ))}
      </div>
      {needle && !matching.length ? <p className="muted-copy">Ничего не найдено.</p> : null}
      {!needle && matching.length > COLLAPSED_COUNT ? (
        <button type="button" className="voiceover-picker__more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Свернуть" : "Показать все (" + matching.length + ")"}
        </button>
      ) : null}
    </div>
  );
}
