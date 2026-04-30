import { useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import type { TabId, UserProfile } from "./lib/types";
import { bootTelegramShell, isTelegramMiniApp } from "./lib/telegram";
import { getProfile } from "./services/api";
import { AccessGate } from "./pages/AccessGate";
import { Schedule } from "./pages/Schedule";
import { Settings } from "./pages/Settings";
import { Subscriptions } from "./pages/Subscriptions";
import { Updates } from "./pages/Updates";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>(() => (localStorage.getItem("miniapp-active-tab") as TabId) || "updates");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    bootTelegramShell();
    if (isTelegramMiniApp()) {
      getProfile().then(setUser);
    }
  }, []);

  function changeTab(tab: TabId) {
    setActiveTab(tab);
    localStorage.setItem("miniapp-active-tab", tab);
  }

  async function refresh() {
    if (!isTelegramMiniApp()) {
      return;
    }
    setRefreshKey((key) => key + 1);
    setRefreshing(true);
    try {
      setUser(await getProfile());
    } finally {
      setRefreshing(false);
    }
  }

  if (!isTelegramMiniApp()) {
    return <AccessGate />;
  }

  return (
    <AppLayout activeTab={activeTab} user={user} refreshing={refreshing} onTabChange={changeTab} onRefresh={refresh}>
      {activeTab === "updates" ? <Updates favoriteVoiceover={user?.favorite_voiceover || "AniLiberty"} refreshKey={refreshKey} /> : null}
      {activeTab === "subscriptions" ? <Subscriptions refreshKey={refreshKey} /> : null}
      {activeTab === "schedule" ? <Schedule refreshKey={refreshKey} /> : null}
      {activeTab === "settings" ? <Settings user={user} onUserUpdated={setUser} /> : null}
    </AppLayout>
  );
}
