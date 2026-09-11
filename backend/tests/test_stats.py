"""Сбор статистики и экран «Статистика» в админке (нужен Postgres)."""
import datetime as dt

import pytest
from aiohttp import web
from sqlalchemy import select, text

import config
from conftest import ADMIN_ID
from database.models import DailyStat, UserActivity
from services import checker, health, parser, scraper_keys, stats
from test_db_flows import add_sub, client, feed, init_data  # noqa: F401 — фикстура client

ANIME_PAGE = """
<div class="text-body-tertiary">Тип</div><div>Сериал</div>
<div class="text-body-tertiary">Статус</div><div>Онгоинг</div>
<div class="text-body-tertiary">Эпизоды</div><div>3 / 12</div>
<div class="text-body-tertiary">Озвучка</div><div><a href="/anime/dubbing/aniliberty">AniLiberty</a></div>
"""


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(health, "home_health", health.HomeHealth())
    monkeypatch.setattr(stats, "_active_marked", set())
    monkeypatch.setattr(checker, "_deferred_counted", set())
    parser._HTML_CACHE.clear()
    yield
    parser._HTML_CACHE.clear()


@pytest.fixture
async def fake_scraper(database, monkeypatch):
    """ScraperAPI на локальном сервере и один рабочий ключ"""
    await database.add_scraper_key("main", None, scraper_keys.encrypt_key("keyokaaaa"), request_count=0, request_limit=1000)
    await scraper_keys.key_pool.reload()

    async def handler(request):
        return web.Response(status=200, text=ANIME_PAGE)

    app = web.Application()
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    monkeypatch.setattr(parser, "SCRAPER_API_URL", f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/")
    yield
    await runner.cleanup()


async def metric_values(db, metric):
    async with db.async_session() as session:
        rows = (await session.execute(select(DailyStat.dimension, DailyStat.value).where(DailyStat.metric == metric))).all()
    return {dimension: value for dimension, value in rows}


async def test_miniapp_requests_are_attributed_and_cached(database, fake_scraper, client, monkeypatch):
    monkeypatch.setattr(config, "ANIMEGO_CACHE_TTL_SECONDS", 300, raising=False)
    headers = init_data(40)

    first = await client.get("/api/miniapp/anime-details", params={"link": "https://animego.me/anime/x-1"}, headers=headers)
    second = await client.get("/api/miniapp/anime-details", params={"link": "https://animego.me/anime/x-1"}, headers=headers)
    assert first.status_code == second.status_code == 200 and first.json()["voiceovers"] == ["AniLiberty"]

    assert await metric_values(database, "scraper.success") == {"miniapp:anime": 1}
    assert await metric_values(database, "cache.hit") == {"miniapp:anime": 1}
    assert (await metric_values(database, "scraper.latency_count")) == {"": 1}
    async with database.async_session() as session:
        activity = (await session.execute(select(UserActivity.user_id, UserActivity.source))).all()
    assert activity == [(40, "miniapp")]


async def test_checker_counts_notifications_and_results(database, fake_bot, monkeypatch):
    url = "https://animego.me/anime/final-stats"
    await add_sub(database, 41, "Финал", url, "AniLiberty", "Серия 12", total=13)
    monkeypatch.setattr(parser, "get_home", feed(("Финал", "Серии 13", "AniLiberty", url)))

    await checker.check_updates(fake_bot)

    assert await metric_values(database, "notifications.sent") == {"": 1}
    assert await metric_values(database, "subscriptions.completed") == {"": 1}
    assert await metric_values(database, "home.result") == {"problem": 1}  # в фейковой странице нет расписания


async def test_stats_endpoint(database, client, monkeypatch, fake_bot):
    async def fake_account(api_key, session):
        return 200, {"requestCount": 250, "requestLimit": 1000}

    monkeypatch.setattr(scraper_keys, "fetch_account", fake_account)
    await database.add_scraper_key("snap", None, scraper_keys.encrypt_key("keysnapaaaa"), request_count=0, request_limit=1000)
    await scraper_keys.refresh_all_keys(None)
    await stats.increment_many([
        ("scraper.success", "checker:home", 5), ("scraper.success", "miniapp:anime", 2),
        ("scraper.failed", "checker:home", 1), ("scraper.failed_status", "500", 1),
        ("scraper.latency_ms", "", 3000), ("scraper.latency_count", "", 6),
        ("notifications.sent", "", 4),
    ])
    await stats.mark_active(50, stats.SOURCE_MINIAPP)
    await stats.mark_active(51, stats.SOURCE_BOT)

    assert (await client.get("/api/miniapp/admin/stats?days=5", headers=init_data(ADMIN_ID))).status_code == 400
    response = await client.get("/api/miniapp/admin/stats?days=7", headers=init_data(ADMIN_ID))
    assert response.status_code == 200
    body = response.json()

    assert len(body["days"]) == 7 and body["days"][-1] == dt.datetime.utcnow().date().isoformat()
    scraper = body["scraper"]
    assert scraper["success_by_source"]["checker"][-1] == 5 and scraper["success_by_source"]["miniapp"][-1] == 2
    assert scraper["success_by_page"]["home"][-1] == 5
    assert scraper["failed"][-1] == 1 and scraper["failed_by_status"]["500"][-1] == 1
    assert scraper["latency_avg_ms"][-1] == 500 and scraper["latency_avg_ms"][0] is None
    assert scraper["credits"] and scraper["credits"][-1]["remaining"] == 750 and scraper["credits"][-1]["limit"] == 1000

    bot = body["bot"]
    assert bot["notifications_sent"][-1] == 4
    assert bot["active_total"][-1] == 2 and bot["active_7d"] == 2
    assert set(bot["active_by_source"]) == {"miniapp", "bot"}

    tables = {table["name"] for table in body["database"]["tables"]}
    assert {"daily_stats", "subscriptions", "scraper_key_snapshots"} <= tables
    assert body["database"]["size_bytes"] > 0 and body["database"]["retention_days"] == 180
    assert body["server"]["memory_total"] > 0 and body["server"]["python"]


async def test_prune_old_stats(database):
    old_day = dt.datetime.utcnow().date() - dt.timedelta(days=stats.STATS_RETENTION_DAYS + 5)
    await database.increment_daily_stats([("notifications.sent", "", 1)], day=old_day)
    await database.increment_daily_stats([("notifications.sent", "", 2)])
    await database.record_user_activity(1, "bot", day=old_day)

    await stats.prune_old_stats()

    async with database.async_session() as session:
        left = (await session.execute(text("SELECT value FROM daily_stats"))).scalars().all()
        activity = await session.scalar(text("SELECT count(*) FROM user_activity"))
    assert left == [2] and activity == 0
