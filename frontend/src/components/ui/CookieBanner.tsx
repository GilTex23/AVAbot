import { useState } from "react";
import { Button } from "./button";

export function CookieBanner() {
  const [visible, setVisible] = useState(() => localStorage.getItem("miniapp-cookie-ok") !== "1");

  if (!visible) {
    return null;
  }

  return (
    <div className="cookie-banner">
      <span>Mini App хранит выбранную вкладку и демо-настройки на этом устройстве.</span>
      <Button
        size="sm"
        onClick={() => {
          localStorage.setItem("miniapp-cookie-ok", "1");
          setVisible(false);
        }}
      >
        Ок
      </Button>
    </div>
  );
}
