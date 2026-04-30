import { CalendarDays, Library, Radio, Settings } from "lucide-react";
import type { TabId } from "../../lib/types";
import { cx } from "../../lib/utils";

const items: Array<{ id: TabId; label: string; icon: typeof Radio }> = [
  { id: "updates", label: "Обновления", icon: Radio },
  { id: "subscriptions", label: "Подписки", icon: Library },
  { id: "schedule", label: "Расписание", icon: CalendarDays },
  { id: "settings", label: "Настройки", icon: Settings },
];

type BottomNavProps = {
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
};

export function BottomNav({ activeTab, onTabChange }: BottomNavProps) {
  return (
    <nav className="bottom-nav" aria-label="Mini App navigation">
      {items.map((item) => {
        const Icon = item.icon;
        const active = activeTab === item.id;
        return (
          <button key={item.id} type="button" className={cx("bottom-nav__item", active && "bottom-nav__item--active")} onClick={() => onTabChange(item.id)}>
            <Icon size={21} />
            <span>{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
