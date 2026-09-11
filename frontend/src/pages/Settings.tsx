import { Check, ChevronRight, Loader2, Save, ShieldCheck, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { saveQuietHours, saveTimeZone, saveVoiceover } from "../services/api";
import type { UserProfile } from "../lib/types";
import { hapticNotification } from "../lib/telegram";
import { voiceovers } from "../lib/utils";
import { DEFAULT_TIME_ZONE, formatTimeZoneLabel, getTimeZones } from "../lib/timezones";

type SettingsProps = {
  user?: UserProfile | null;
  onUserUpdated: (user: UserProfile | null) => void;
  onOpenAdmin: () => void;
};

export function Settings({ user, onUserUpdated, onOpenAdmin }: SettingsProps) {
  const [voiceover, setVoiceover] = useState(user?.favorite_voiceover || "AniLiberty");
  const [quietMode, setQuietMode] = useState(user?.quiet_hours_enabled || false);
  const [quietStart, setQuietStart] = useState(user?.quiet_hours_start || "23:00");
  const [quietEnd, setQuietEnd] = useState(user?.quiet_hours_end || "09:00");
  const [timezone, setTimezone] = useState(user?.quiet_timezone || DEFAULT_TIME_ZONE);
  const [savingVoiceover, setSavingVoiceover] = useState(false);
  const [savingTimezone, setSavingTimezone] = useState(false);
  const [savingQuiet, setSavingQuiet] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const timeZones = useMemo(() => {
    const zones = getTimeZones();
    // Сохранённый пояс может не входить в список браузера (например, устаревшее имя) — показываем и его
    return user?.quiet_timezone && !zones.includes(user.quiet_timezone) ? [user.quiet_timezone, ...zones] : zones;
  }, [user?.quiet_timezone]);
  const savedTimezone = user?.quiet_timezone || DEFAULT_TIME_ZONE;

  useEffect(() => {
    setVoiceover(user?.favorite_voiceover || "AniLiberty");
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

  async function saveFavoriteVoiceover() {
    setSavingVoiceover(true);
    setNotice(null);
    try {
      const result = await saveVoiceover(voiceover);
      onUserUpdated(user ? { ...user, favorite_voiceover: result.favorite_voiceover } : null);
      hapticNotification("success");
      setNotice("Озвучка сохранена.");
    } catch {
      hapticNotification("error");
      setNotice("Не удалось сохранить озвучку.");
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
        <h2>Любимая озвучка</h2>
        <div className="chip-row chip-row--wrap">
          {voiceovers.map((item) => (
            <button key={item} className={item === voiceover ? "chip chip--active" : "chip"} type="button" onClick={() => setVoiceover(item)}>
              {item}
            </button>
          ))}
        </div>
        <Button variant="primary" disabled={savingVoiceover} onClick={saveFavoriteVoiceover}>
          {savingVoiceover ? <Loader2 className="spin" size={17} /> : user?.favorite_voiceover === voiceover ? <Check size={17} /> : <Save size={17} />}
          {savingVoiceover ? "Сохраняю" : "Сохранить озвучку"}
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
