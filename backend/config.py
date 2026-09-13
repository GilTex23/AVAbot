import os
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

try:
    load_dotenv()
    logger.info("The virtual environment is loaded")

    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = [int(id_) for id_ in os.getenv("ADMIN_IDS", "").split(",") if id_]
    DATABASE_URL = os.getenv("DATABASE_URL")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    ADMIN_PANEL_USER = os.getenv("ADMIN_PANEL_USER", "admin")
    ADMIN_PANEL_PASS = os.getenv("ADMIN_PANEL_PASS", "admin")
    ADMIN_PANEL_SECRET = os.getenv("ADMIN_PANEL_SECRET", "super-secret-key")

    ANIMEGO_DIRECT_ENABLED = os.getenv("ANIMEGO_DIRECT_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    ANIMEGO_DIRECT_TIMEOUT_SECONDS = float(os.getenv("ANIMEGO_DIRECT_TIMEOUT_SECONDS", "1.5"))
    ANIMEGO_CACHE_TTL_SECONDS = int(os.getenv("ANIMEGO_CACHE_TTL_SECONDS", "300"))
    # ScraperAPI рекомендует ждать ответа не меньше 60–70 секунд
    SCRAPER_API_TIMEOUT_SECONDS = float(os.getenv("SCRAPER_API_TIMEOUT_SECONDS", "70"))
    MINIAPP_DEV_AUTH_ENABLED = os.getenv("MINIAPP_DEV_AUTH_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    # Публичный HTTPS-адрес мини-аппа: кнопка «Открыть приложение» в боте и кнопка меню чата.
    # Пусто — бот работает только через меню в чате, кнопку меню не трогает
    MINIAPP_URL = os.getenv("MINIAPP_URL", "").strip()
    if MINIAPP_URL and not MINIAPP_URL.startswith("https://"):
        logger.warning("MINIAPP_URL must start with https:// — Telegram opens mini apps only over HTTPS; ignoring it")
        MINIAPP_URL = ""

    # Shikimori: число серий, статус и время выхода оригинала для тайтлов с подписками (бесплатно, без ScraperAPI)
    SHIKIMORI_ENABLED = os.getenv("SHIKIMORI_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    SHIKIMORI_URL = os.getenv("SHIKIMORI_URL", "https://shikimori.io").rstrip("/")
    # Shikimori просит указывать в User-Agent название приложения
    SHIKIMORI_USER_AGENT = os.getenv("SHIKIMORI_USER_AGENT", "AnimeVoiceNotifier")

    # YummyAnime: второй источник серий в озвучке (свой API, без ScraperAPI)
    YUMMY_ENABLED = os.getenv("YUMMY_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    YUMMY_API_URL = os.getenv("YUMMY_API_URL", "https://api.yani.tv").rstrip("/")
    YUMMY_SITE_URL = os.getenv("YUMMY_SITE_URL", "https://yummyani.me").rstrip("/")
    # Публичный токен приложения (yummyani.me/dev/applications); API просит передавать его в X-Application
    YUMMY_APP_TOKEN = os.getenv("YUMMY_APP_TOKEN", "").strip()

    # Шифрует ключи ScraperAPI в БД. Если его поменять, сохранённые ключи перестанут расшифровываться
    SCRAPER_KEYS_SECRET = os.getenv("SCRAPER_KEYS_SECRET", "")
    if not SCRAPER_KEYS_SECRET:
        raise ValueError("SCRAPER_KEYS_SECRET is required: it encrypts ScraperAPI keys stored in the database")

    # Устаревший способ: ключи из .env (NAME-API_KEY, NAME2-API_KEY) импортируются в БД при первом запуске,
    # дальше они управляются из админки мини-аппа
    SCRAPER_API_KEYS = [
        tuple(part.strip() for part in item.rsplit('-', 1)) if '-' in item else (f"env-{index}", item)
        for index, item in enumerate(
            (item.strip() for item in os.getenv('SCRAPER_API_KEYS', '').split(',') if item.strip()), start=1
        )
    ]

    logger.info("The virtual environment is installed")
except Exception as e:
    logger.error(f"Error env installing: {e}")
    raise e
