import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Конфиг читается при импорте модулей бэкенда, поэтому тестовое окружение задаётся до любых импортов.
# Тесты с базой запускаются, только если задан TEST_DATABASE_URL (в CI — сервис postgres).
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
os.environ.update({
    "BOT_TOKEN": "123456:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz",
    "ADMIN_IDS": "111",
    "DATABASE_URL": TEST_DATABASE_URL or "postgresql+asyncpg://test:test@localhost:5432/test",
    "WEBHOOK_URL": "https://example.com",
    "WEBHOOK_PATH": "/webhook/test",
    "SCRAPER_KEYS_SECRET": "test-secret-for-tests",
    "SCRAPER_API_KEYS": "",
    "ANIMEGO_DIRECT_ENABLED": "false",
    "ANIMEGO_CACHE_TTL_SECONDS": "0",
    "MINIAPP_DEV_AUTH_ENABLED": "false",
})
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

ADMIN_ID = 111


class FakeBot:
    """Вместо Telegram: запоминает отправленные сообщения"""

    def __init__(self):
        self.sent = []

    async def send_message(self, *args, **kwargs):
        chat_id = kwargs.get("chat_id", args[0] if args else None)
        text = kwargs.get("text", args[1] if len(args) > 1 else None)
        self.sent.append({"chat_id": chat_id, "text": text, "silent": kwargs.get("disable_notification")})

    def texts_for(self, chat_id):
        return [message["text"] for message in self.sent if message["chat_id"] == chat_id]


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture(autouse=True)
def no_stats_writes_without_database(request, monkeypatch):
    """Тесты без базы не должны писать статистику: иначе соединения к Postgres остаются в пуле чужого event loop"""
    if "database" in request.fixturenames:
        return
    from database import requests as db

    async def skip(*args, **kwargs):
        return None

    for name in ("increment_daily_stats", "record_user_activity", "add_key_snapshots", "touch_voiceovers", "upsert_anime_titles"):
        monkeypatch.setattr(db, name, skip)


@pytest.fixture(scope="session")
def fixture_html():
    def read(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return read


@pytest.fixture(scope="session")
def migrated_database():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set")
    # Отдельный процесс: alembic и движок SQLAlchemy не должны делить event loop с тестами
    subprocess.run([sys.executable, "-m", "scripts.migrate"], cwd=BACKEND_DIR, env=os.environ, check=True)


@pytest.fixture
async def database(migrated_database):
    from sqlalchemy import text
    from database import requests as db
    from services.scraper_keys import key_pool

    async with db.engine.begin() as conn:
        await conn.execute(text(
            "TRUNCATE episode_releases, episode_airings, scraper_api_key_usage, scraper_key_snapshots, scraper_api_keys, "
            "daily_stats, user_activity, subscriptions, users, voiceovers, anime_titles RESTART IDENTITY CASCADE"
        ))
    await key_pool.reload()
    yield db
    # Соединения пула привязаны к event loop теста
    await db.engine.dispose()
