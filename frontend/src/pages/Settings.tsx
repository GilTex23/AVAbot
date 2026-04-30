import { Save, SlidersHorizontal } from "lucide-react";
import { useState } from "react";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { saveVoiceover } from "../services/api";
import type { UserProfile } from "../lib/types";
import { voiceovers } from "../lib/utils";

type SettingsProps = {
  user?: UserProfile | null;
  onVoiceoverSaved: (voiceover: string) => void;
};

export function Settings({ user, onVoiceoverSaved }: SettingsProps) {
  const [voiceover, setVoiceover] = useState(user?.favorite_voiceover || "AniLiberty");
  const [quietMode, setQuietMode] = useState(false);

  async function save() {
    const result = await saveVoiceover(voiceover);
    onVoiceoverSaved(result.favorite_voiceover);
  }

  return (
    <div className="page-stack">
      <section className="section-title">
        <h1>Настройки</h1>
        <p>Профиль Mini App и любимая озвучка</p>
      </section>

      <Card className="settings-card">
        <div className="settings-card__head">
          <SlidersHorizontal size={22} />
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
        <Button variant="primary" onClick={save}>
          <Save size={17} />
          Сохранить
        </Button>
      </Card>

      <Card className="settings-card settings-card--column">
        <Switch checked={quietMode} onChange={setQuietMode} label="Тихий режим" />
        <p className="muted-copy">Этот переключатель уже живой в интерфейсе; backend-настройку добавим следующим шагом.</p>
      </Card>
    </div>
  );
}
