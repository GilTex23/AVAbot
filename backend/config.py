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
    MINIAPP_DEV_AUTH_ENABLED = os.getenv("MINIAPP_DEV_AUTH_ENABLED", "false").lower() in ("1", "true", "yes", "on")

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
