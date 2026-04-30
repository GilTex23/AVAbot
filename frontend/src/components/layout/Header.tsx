import { RefreshCw } from "lucide-react";
import { Button } from "../ui/button";
import type { UserProfile } from "../../lib/types";

type HeaderProps = {
  user?: UserProfile | null;
  onRefresh: () => void;
};

export function Header({ user, onRefresh }: HeaderProps) {
  return (
    <header className="header">
      <div className="brand">
        <span className="brand__name">Anime Notify</span>
        <span className="brand__caption">данные animego.me</span>
      </div>

      <div className="header__actions">
        <Button size="icon" variant="ghost" onClick={onRefresh} aria-label="Обновить">
          <RefreshCw size={20} />
        </Button>
        <div className="avatar" title={user?.username || "Telegram user"}>
          {user?.photo_url ? <img src={user.photo_url} alt={user?.username || "Telegram user"} /> : (user?.username || "A").slice(0, 1).toUpperCase()}
        </div>
      </div>
    </header>
  );
}
