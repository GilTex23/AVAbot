import { ExternalLink, ShieldCheck } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { botUrl } from "../lib/config";
import { openTelegramLink } from "../lib/telegram";

export function AccessGate() {
  return (
    <main className="gate">
      <Card className="gate__card">
        <div className="gate__icon">
          <ShieldCheck size={32} />
        </div>
        <h1>Открой мини-приложение в Telegram</h1>
        <p>
          Бот следит за новыми сериями, расписанием выхода и выбранными озвучками. Данные берутся с сайта animego.me, а доступ к настройкам
          подписок защищен через Telegram.
        </p>
        <Button variant="primary" onClick={() => openTelegramLink(botUrl)}>
          <ExternalLink size={17} />
          Перейти к боту
        </Button>
      </Card>
    </main>
  );
}
