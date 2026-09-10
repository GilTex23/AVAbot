import { useCallback, useEffect, useState } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import type { TabId, UserProfile } from "./lib/types";
import { bootTelegramShell, hapticNotification, isTelegramMiniApp, requestWriteAccessOnce, showTelegramAlert } from "./lib/telegram";
import { getProfile } from "./services/api";
import { AccessGate } from "./pages/AccessGate";
import { Admin } from "./pages/Admin";
import { Schedule } from "./pages/Schedule";
import { Settings } from "./pages/Settings";
import { Subscriptions } from "./pages/Subscriptions";
import { Updates } from "./pages/Updates";

export default function App() {
  const [activeTab, setActiveTab] = useState<TabId>(() => (localStorage.getItem("miniapp-active-tab") as TabId) || "updates");
  const [user, setUser] = useState<UserProfile | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [adminOpen, setAdminOpen] = useState(false);
  const closeAdmin = useCallback(() => setAdminOpen(false), []);

  useEffect(() => {
    bootTelegramShell();
    if (isTelegramMiniApp()) {
      getProfile()
        .then((profile) => {
          setUser(profile);
          requestWriteAccessOnce();
        })
        .catch(() => {
          hapticNotification("error");
          showTelegramAlert("Не удалось загрузить профиль mini app. Попробуйте открыть приложение ещё раз.");
        });
    }
  }, []);

  function changeTab(tab: TabId) {
    setActiveTab(tab);
    setAdminOpen(false);
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
      hapticNotification("success");
    } catch {
      hapticNotification("error");
      showTelegramAlert("Не удалось обновить данные. Попробуйте ещё раз.");
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
      {activeTab === "settings" && adminOpen && user?.is_admin ? <Admin refreshKey={refreshKey} onBack={closeAdmin} /> : null}
      {activeTab === "settings" && !(adminOpen && user?.is_admin) ? (
        <Settings user={user} onUserUpdated={setUser} onOpenAdmin={() => setAdminOpen(true)} />
      ) : null}
    </AppLayout>
  );
}
