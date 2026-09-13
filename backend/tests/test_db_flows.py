"""Сценарии с настоящей базой (Postgres). Без TEST_DATABASE_URL пропускаются."""
import datetime as dt
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import httpx
import pytest
from aiohttp import web
from bs4 import BeautifulSoup
from fastapi import FastAPI
from sqlalchemy import select, text

import config
from conftest import ADMIN_ID
from database.models import EpisodeRelease, Subscription, User
from services import checker, forecast, health, parser, scraper_keys

FETCHED_AT = dt.datetime(2026, 9, 11, 13, 49, tzinfo=parser.MSK)


@pytest.fixture(autouse=True)
def fresh_health(monkeypatch):
    monkeypatch.setattr(health, "home_health", health.HomeHealth())


async def add_sub(db, user_id, title, url, voiceover, last_episode, total=None, days_ago=0, quiet=False, checked_days_ago=0):
    now = dt.datetime.utcnow()
    moscow_now = dt.datetime.now(parser.MSK)
    async with db.async_session() as session:
        if not await session.get(User, user_id):
            # Тихие часы — окно вокруг текущего московского времени, чтобы тест не зависел от часа запуска
            session.add(User(
                id=user_id, username=f"u{user_id}", quiet_hours_enabled=quiet,
                quiet_hours_start=f"{moscow_now - dt.timedelta(hours=2):%H:%M}",
                quiet_hours_end=f"{moscow_now + dt.timedelta(hours=2):%H:%M}",
                quiet_timezone="Europe/Moscow",
            ))
            await session.flush()
        sub = Subscription(
            user_id=user_id, anime_title=title, anime_url=url, voiceover=voiceover, last_episode=last_episode,
            total_episodes=total, last_episode_at=now - dt.timedelta(days=days_ago),
            info_checked_at=now - dt.timedelta(days=checked_days_ago),
        )
        session.add(sub)
        await session.commit()
        return sub.id


async def get_sub(db, sub_id):
    async with db.async_session() as session:
        return await session.get(Subscription, sub_id)


def feed(*items):
    async def fake_home(bot):
        return {
            "updates": [
                {"title": title, "episode": episode, "studio": studio, "link": link, "poster_url": "",
                 "released_at": dt.datetime.utcnow()}
                for title, episode, studio, link in items
            ],
            "schedule": [],
            "timezone": "Москва",
            "timezone_known": True,
        }
    return fake_home


async def test_notification_and_finish_on_last_episode(database, fake_bot, monkeypatch):
    url = "https://animego.me/anime/final-1"
    sub_id = await add_sub(database, 4, "Финал", url, "AniLiberty", "Серия 12", total=13)
    monkeypatch.setattr(parser, "get_home", feed(("Финал", "Серии 13", "AniLiberty", url)))

    await checker.check_updates(fake_bot)

    texts = fake_bot.texts_for(4)
    assert len(texts) == 2 and "Серия:</b> 13 из 13" in texts[0] and "завершено" in texts[1]
    assert await get_sub(database, sub_id) is None
    async with database.async_session() as session:
        assert await session.scalar(select(EpisodeRelease.episode).where(EpisodeRelease.anime_url == url)) == 13


async def test_batch_release_notified_once(database, fake_bot, monkeypatch):
    url = "https://animego.me/anime/rassekaya-nebosvod-3754"
    sub_id = await add_sub(database, 6, "Рассекая небосвод", url, "MDA", "Серии 6", total=26)
    monkeypatch.setattr(parser, "get_home", feed(("Рассекая небосвод", "Серии 1, 7-8", "MDA", url)))

    await checker.check_updates(fake_bot)
    await checker.check_updates(fake_bot)

    texts = fake_bot.texts_for(6)
    assert len(texts) == 1 and "Серии:</b> 7–8 из 26" in texts[0]
    assert (await get_sub(database, sub_id)).last_episode == "Серия 8"


async def test_quiet_hours_notification_is_delivered_later(database, fake_bot, monkeypatch):
    """Серия вышла ночью и ушла из ленты до конца тихих часов — уведомление всё равно приходит"""
    url = "https://animego.me/anime/night-1"
    sub_id = await add_sub(database, 8, "Ночной тайтл", url, "AniLiberty", "Серия 4", total=12, quiet=True)

    monkeypatch.setattr(parser, "get_home", feed(("Ночной тайтл", "Серии 5", "AniLiberty", url)))
    await checker.check_updates(fake_bot)
    assert fake_bot.texts_for(8) == []

    async with database.async_session() as session:
        await session.execute(text("UPDATE users SET quiet_hours_enabled = false WHERE id = 8"))
        await session.commit()
    monkeypatch.setattr(parser, "get_home", feed())  # в ленте этой серии уже нет
    await checker.check_updates(fake_bot)

    texts = fake_bot.texts_for(8)
    assert len(texts) == 1 and "Серия:</b> 5 из 12" in texts[0]
    assert (await get_sub(database, sub_id)).last_episode == "Серия 5"


async def test_other_voiceover_is_ignored(database, fake_bot, monkeypatch):
    url = "https://animego.me/anime/other-vo"
    await add_sub(database, 9, "Тайтл", url, "AniLiberty", "Серия 4")
    monkeypatch.setattr(parser, "get_home", feed(("Тайтл", "Серии 5", "AnimeVost", url)))
    await checker.check_updates(fake_bot)
    assert fake_bot.texts_for(9) == []


async def test_record_home_from_real_page(database, fixture_html):
    soup = BeautifulSoup(fixture_html("animego_home_moscow.html"), "html.parser")
    label, zone = parser._page_timezone(soup)
    home = {
        "updates": parser._parse_updates(soup, FETCHED_AT, zone),
        "schedule": parser._parse_schedule(soup, FETCHED_AT, zone),
    }
    target = home["schedule"][0]["items"][0]  # серия 11 (из 12)
    sub_id = await add_sub(database, 7, target["title"], target["link"], "AniLiberty", "Серия 10")

    subs = await database.get_all_subscriptions()
    await forecast.record_home(home, subs)
    await forecast.record_home(home, subs)  # повтор ничего не дублирует

    async with database.async_session() as session:
        mda = (await session.execute(text(
            "SELECT episode FROM episode_releases WHERE studio = 'MDA' AND anime_url LIKE '%rassekaya%' ORDER BY episode"
        ))).scalars().all()
    assert mda == [1, 2, 3, 4, 5, 6, 7, 8]
    assert (await get_sub(database, sub_id)).total_episodes == 12  # «(из 12)» из расписания


async def test_subscriptions_status_check(database, fake_bot, monkeypatch):
    a, c, d = ("https://animego.me/anime/a", "https://animego.me/anime/c", "https://animego.me/anime/d")
    ids = {
        "done_unknown_total": await add_sub(database, 1, "Ледяная стена", a, "AniLiberty", "14 серия", None, checked_days_ago=8),
        "lagging": await add_sub(database, 1, "Ледяная стена", a, "ТО Дубляжная", "Серия 10", None, checked_days_ago=8),
        "stale_released": await add_sub(database, 2, "Брошенное", c, "AniDUB", "Серия 12", 14, days_ago=40, checked_days_ago=8),
        "stale_ongoing": await add_sub(database, 2, "Онгоинг", d, "AniDUB", "Серия 5", None, days_ago=40, checked_days_ago=8),
        "done_known_total": await add_sub(database, 3, "Готово", "https://animego.me/anime/e", "AniDUB", "Серия 12", 12),
        "fresh": await add_sub(database, 3, "Свежее", "https://animego.me/anime/f", "AniDUB", "Серия 3", None),
    }
    pages = {
        a: {"status": "Вышел", "type": "Сериал", "total_episodes": 14},
        c: {"status": "Вышел", "type": "Сериал", "total_episodes": 14},
        d: {"status": "Онгоинг", "type": "Сериал", "total_episodes": None},
    }
    requested = []

    async def fake_info(url, bot):
        requested.append(url)
        return pages.get(url)

    monkeypatch.setattr(parser, "get_anime_info", fake_info)
    stats = await checker.check_subscriptions_status(fake_bot)

    assert sorted(requested) == sorted(pages)  # «Свежее» проверяли меньше недели назад — страницу не трогаем
    alive = {name for name, sub_id in ids.items() if await get_sub(database, sub_id)}
    assert alive == {"lagging", "stale_ongoing", "fresh"}
    assert (await get_sub(database, ids["lagging"])).total_episodes == 14
    assert stats == {"checked_urls": 3, "failed_urls": 0, "shikimori_urls": 0, "updated_totals": 2, "completed": 2, "stale": 1}

    requested.clear()
    await checker.check_subscriptions_status(fake_bot)
    assert requested == []  # только что проверенные страницы повторно не запрашиваются


def init_data(user_id, age=0):
    pairs = {"auth_date": str(int(time.time()) - age), "user": json.dumps({"id": user_id, "first_name": "T"})}
    data_check = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return {"X-Telegram-Init-Data": urlencode(pairs)}


@pytest.fixture
async def client():
    from api.admin import router as admin_router
    from api.miniapp import router as miniapp_router
    app = FastAPI()
    app.include_router(miniapp_router)
    app.include_router(admin_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        yield http


async def test_add_subscription_rules(database, client, monkeypatch):
    pages = {
        "https://animego.me/anime/film": {"type": "Фильм", "status": "Вышел", "total_episodes": 1},
        "https://animego.me/anime/lagging": {"type": "Сериал", "status": "Вышел", "total_episodes": 14},
    }

    async def fake_info(url, bot):
        return pages[url]

    monkeypatch.setattr(parser, "get_anime_info", fake_info)

    async def add(link, episode):
        return await client.post("/api/miniapp/subscriptions", headers=init_data(20), json={
            "title": "T", "link": link, "episode": episode, "voiceover": "AniLiberty",
        })

    film = await add("https://animego.me/anime/film", "Серия 1")
    assert film.status_code == 400 and "фильм" in film.json()["detail"]
    complete = await add("https://animego.me/anime/lagging", "Серии 14")
    assert complete.status_code == 400 and "все серии" in complete.json()["detail"]
    lagging = await add("https://animego.me/anime/lagging", "Серии 12")
    assert lagging.status_code == 200 and lagging.json()["created"] is True


async def test_my_week(database, client):
    url = "https://animego.me/anime/week-1"
    now = dt.datetime.utcnow().replace(second=0, microsecond=0)
    next_air = now + dt.timedelta(days=2)
    await add_sub(database, 21, "Недельный", url, "AniLiberty", "Серия 3", total=12)
    await add_sub(database, 21, "Без истории", "https://animego.me/anime/none", "AniLiberty", "Серия 1")
    await database.record_episode_airings([
        {"anime_url": url, "episode": n, "air_at": next_air - (4 - n) * forecast.WEEK} for n in (1, 2, 3, 4)
    ])
    await database.record_episode_releases([
        {"anime_url": url, "anime_title": "Недельный", "studio": "AniLiberty", "episode": n,
         "released_at": next_air - (4 - n) * forecast.WEEK + dt.timedelta(hours=20)} for n in (1, 2, 3)
    ])

    response = await client.get("/api/miniapp/my-week", headers=init_data(21))
    items = response.json()["items"]
    assert response.status_code == 200 and [item["title"] for item in items] == ["Недельный"]
    assert items[0]["forecast"]["episode"] == 4 and items[0]["forecast"]["basis"] == "title"


async def test_user_timezone_settings_and_schedule(database, client, monkeypatch, fixture_html):
    soup = BeautifulSoup(fixture_html("animego_home_moscow.html"), "html.parser")
    schedule = parser._parse_schedule(soup, FETCHED_AT, parser._page_zone(soup))

    async def fake_schedule(bot):
        return schedule

    monkeypatch.setattr(parser, "get_schedule", fake_schedule)
    headers = init_data(30)

    moscow = (await client.get("/api/miniapp/schedule", headers=headers)).json()["days"]
    assert moscow[0]["items"][0]["time"] == "14:57 (Москва)"  # по умолчанию

    assert (await client.put("/api/miniapp/settings/timezone", headers=headers, json={"timezone": "Нет/Такого"})).status_code == 400
    saved = await client.put("/api/miniapp/settings/timezone", headers=headers, json={"timezone": "Asia/Yekaterinburg"})
    assert saved.json() == {"quiet_timezone": "Asia/Yekaterinburg"}

    local = (await client.get("/api/miniapp/schedule", headers=headers)).json()["days"]
    assert local[0]["items"][0]["time"] == "16:57 (Екатеринбург)"

    # Тихие часы без пояса (новый клиент) пояс не сбрасывают
    await client.put("/api/miniapp/settings/quiet-hours", headers=headers, json={"enabled": True, "start": "23:00", "end": "08:00"})
    assert (await client.get("/api/miniapp/me", headers=headers)).json()["quiet_timezone"] == "Asia/Yekaterinburg"


async def test_admin_api(database, client, monkeypatch):
    async def fake_account(api_key, session):
        return (401, "Unauthorized") if api_key.startswith("bad") else (200, {"requestCount": 120, "requestLimit": 1000})

    monkeypatch.setattr(scraper_keys, "fetch_account", fake_account)

    assert (await client.get("/api/miniapp/admin/keys")).status_code == 401
    assert (await client.get("/api/miniapp/admin/keys", headers=init_data(222))).status_code == 403
    assert (await client.get("/api/miniapp/admin/keys", headers=init_data(ADMIN_ID, age=7200))).status_code == 401

    added = await client.post("/api/miniapp/admin/keys", headers=init_data(ADMIN_ID),
                              json={"name": "Main", "email": "me@mail.ru", "key": "goodkey12345678"})
    body = added.json()
    assert added.status_code == 200 and "goodkey12345678" not in added.text
    assert body["keys"][0]["masked_key"] == "good…5678" and body["summary"]["remaining"] == 880
    assert "parser_health" in body and "problems" in body["parser_health"]

    duplicate = await client.post("/api/miniapp/admin/keys", headers=init_data(ADMIN_ID), json={"name": "D", "key": "goodkey12345678"})
    assert duplicate.status_code == 409
    rejected = await client.post("/api/miniapp/admin/keys", headers=init_data(ADMIN_ID), json={"name": "B", "key": "badkey12345"})
    assert rejected.status_code == 400


async def test_key_rotation_skips_dead_keys(database, fake_bot, monkeypatch):
    enc = scraper_keys.encrypt_key
    await database.add_scraper_key("k401", None, enc("key401aaaa"), request_count=0, request_limit=1000)
    await database.add_scraper_key("k403", None, enc("key403aaaa"), request_count=100, request_limit=1000)
    await database.add_scraper_key("kok", None, enc("keyokaaaa"), request_count=500, request_limit=1000)
    await scraper_keys.key_pool.reload()

    async def handler(request):
        key = request.query.get("api_key")
        if key == "key401aaaa":
            return web.Response(status=401, text="Unauthorized")
        if key == "key403aaaa":
            return web.Response(status=403, text="You have exhausted the API Credits")
        return web.Response(status=200, text="<html>animego</html>")

    app = web.Application()
    app.router.add_get("/", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setattr(parser, "SCRAPER_API_URL", f"http://127.0.0.1:{port}/")
    try:
        assert await parser.get_html("https://animego.me/anime/rotation", bot=fake_bot) == "<html>animego</html>"
    finally:
        await runner.cleanup()

    statuses = {row.name: row.status for row in await database.get_scraper_keys()}
    assert statuses == {"k401": "invalid", "k403": "exhausted", "kok": "active"}
    admin_texts = " ".join(fake_bot.texts_for(ADMIN_ID))
    assert "k401" in admin_texts and "k403" in admin_texts
