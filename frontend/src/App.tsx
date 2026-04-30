import { useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import type { TabId, UserProfile } from "./lib/types";
import { bootTelegramShell } from "./lib/telegram";
import { getProfile } from "./services/api";
import { Schedule } from "./pages/Schedule";
import { Settings } from "./pages/Settings";
import { Subscriptions } from "./pages/Subscriptions";
import { Updates } from "./pages/Updates";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>(() => (localStorage.getItem("miniapp-active-tab") as TabId) || "updates");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    bootTelegramShell();
    getProfile().then(setUser);
  }, []);

  function changeTab(tab: TabId) {
    setActiveTab(tab);
    localStorage.setItem("miniapp-active-tab", tab);
  }

  function refresh() {
    setRefreshKey((key) => key + 1);
    getProfile().then(setUser);
  }

  return (
    <AppLayout activeTab={activeTab} user={user} onTabChange={changeTab} onRefresh={refresh}>
      {activeTab === "updates" ? <Updates favoriteVoiceover={user?.favorite_voiceover || "AniLiberty"} refreshKey={refreshKey} /> : null}
      {activeTab === "subscriptions" ? <Subscriptions refreshKey={refreshKey} /> : null}
      {activeTab === "schedule" ? <Schedule refreshKey={refreshKey} /> : null}
      {activeTab === "settings" ? <Settings user={user} onVoiceoverSaved={(voiceover) => setUser((current) => (current ? { ...current, favorite_voiceover: voiceover } : current))} /> : null}
    </AppLayout>
  );
}
