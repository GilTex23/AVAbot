import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(id_) for id_ in os.getenv("ADMIN_IDS", "").split(",") if id_]
DATABASE_URL = os.getenv("DATABASE_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")