import { Save, SlidersHorizontal } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { saveQuietHours, saveVoiceover } from "../services/api";
import type { UserProfile } from "../lib/types";
import { voiceovers } from "../lib/utils";
import { formatTimeZoneLabel, getTimeZones } from "../lib/timezones";

type SettingsProps = {
  user?: UserProfile | null;
  onUserUpdated: (user: UserProfile | null) => void;
};

export function Settings({ user, onUserUpdated }: SettingsProps) {
  const [voiceover, setVoiceover] = useState(user?.favorite_voiceover || "AniLiberty");
  const [quietMode, setQuietMode] = useState(user?.quiet_hours_enabled || false);
  const [quietStart, setQuietStart] = useState(user?.quiet_hours_start || "23:00");
  const [quietEnd, setQuietEnd] = useState(user?.quiet_hours_end || "09:00");
  const [timezone, setTimezone] = useState(user?.quiet_timezone || "Europe/Moscow");
  const timeZones = useMemo(() => getTimeZones(), []);

  useEffect(() => {
    setVoiceover(user?.favorite_voiceover || "AniLiberty");
    setQuietMode(user?.quiet_hours_enabled || false);
    setQuietStart(user?.quiet_hours_start || "23:00");
    setQuietEnd(user?.quiet_hours_end || "09:00");
    setTimezone(user?.quiet_timezone || "Europe/Moscow");
  }, [user]);

  async function saveFavoriteVoiceover() {
    const result = await saveVoiceover(voiceover);
    onUserUpdated(user ? { ...user, favorite_voiceover: result.favorite_voiceover } : null);
  }

  async function saveQuietSettings() {
    const result = await saveQuietHours({
      enabled: quietMode,
      start: quietStart,
      end: quietEnd,
      timezone,
    });
    onUserUpdated(
      user
        ? {
            ...user,
            quiet_hours_enabled: result.quiet_hours_enabled,
            quiet_hours_start: result.quiet_hours_start,
            quiet_hours_end: result.quiet_hours_end,
            quiet_timezone: result.quiet_timezone,
          }
        : null,
    );
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Настройки</h1>
        <p>Профиль Telegram, озвучка и тихие часы</p>
      </section>

      <Card className="settings-card">
        <div className="settings-card__head">
          {user?.photo_url ? <img className="settings-card__avatar" src={user.photo_url} alt={user?.username || "Telegram user"} /> : <SlidersHorizontal size={22} />}
          <div>
            <h2>{user?.username ? `@${user.username}` : "Telegram профиль"}</h2>
            <p>ID {user?.id || "не определен"}</p>
          </div>
        </div>
        <Badge tone="green">{user?.subscriptions_count || 0} подписок</Badge>
      </Card>

      <Card className="settings-card settings-card--column">
        <h2>Любимая озвучка</h2>
        <div className="chip-row chip-row--wrap">
          {voiceovers.map((item) => (
            <button key={item} className={item === voiceover ? "chip chip--active" : "chip"} type="button" onClick={() => setVoiceover(item)}>
              {item}
            </button>
          ))}
        </div>
        <Button variant="primary" onClick={saveFavoriteVoiceover}>
          <Save size={17} />
          Сохранить озвучку
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
        <label className="field-stack">
          <span>Часовой пояс</span>
          <select className="input select" value={timezone} onChange={(event) => setTimezone(event.target.value)}>
            {timeZones.map((item) => (
              <option key={item} value={item}>
                {formatTimeZoneLabel(item)}
              </option>
            ))}
          </select>
        </label>
        <p className="muted-copy">По умолчанию используется Europe/Moscow, то есть UTC+3.</p>
        <Button variant="primary" onClick={saveQuietSettings}>
          <Save size={17} />
          Сохранить тихие часы
        </Button>
      </Card>
    </div>
  );
}
