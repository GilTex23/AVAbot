import type { ReactNode } from "react";
import { BottomNav } from "./BottomNav";
import { Header } from "./Header";
import { CookieBanner } from "../ui/CookieBanner";
import type { TabId, UserProfile } from "../../lib/types";

type AppLayoutProps = {
  activeTab: TabId;
  user?: UserProfile | null;
  children: ReactNode;
  onTabChange: (tab: TabId) => void;
  onRefresh: () => void;
};

export function AppLayout({ activeTab, user, children, onTabChange, onRefresh }: AppLayoutProps) {
  return (
    <div className="app-shell">
      <Header user={user} onRefresh={onRefresh} />
      <main className="app-main">{children}</main>
      <CookieBanner />
      <BottomNav activeTab={activeTab} onTabChange={onTabChange} />
    </div>
  );
}
