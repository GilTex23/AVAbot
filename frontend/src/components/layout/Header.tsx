import { RefreshCw } from "lucide-react";
import { Button } from "../ui/button";
import type { UserProfile } from "../../lib/types";

type HeaderProps = {
  user?: UserProfile | null;
  refreshing?: boolean;
  onRefresh: () => void;
};

export function Header({ user, refreshing = false, onRefresh }: HeaderProps) {
  return (
    <header className="header">
      <div className="brand">
        <span className="brand__name">Anime Notify</span>
        <span className="brand__caption">данные animego.me</span>
      </div>

      <div className="header__actions">
        <Button size="icon" variant="ghost" disabled={refreshing} onClick={onRefresh} aria-label="Обновить">
          <RefreshCw className={refreshing ? "spin" : undefined} size={20} />
        </Button>
        <div className="avatar" title={user?.username || "Telegram user"}>
          {user?.photo_url ? <img src={user.photo_url} alt={user?.username || "Telegram user"} /> : (user?.username || "A").slice(0, 1).toUpperCase()}
        </div>
      </div>
    </header>
  );
}
