"""YummyAnime как второй источник: названия озвучек, подписка, новые серии, проверка подписок и бот."""
import copy
import datetime as dt
import json

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage
from aiohttp import web
from sqlalchemy import select

import config
from conftest import ADMIN_ID, FIXTURES_DIR
from database.models import EpisodeAiring, Subscription
from services import checker, parser, voiceovers, yummy, yummy_sync
from test_bot_voiceovers import USER_ID, button, buttons, telegram  # noqa: F401 — фикстура telegram
from test_db_flows import add_sub, client, feed, get_sub, init_data  # noqa: F401 — фикстура client

DATA = json.loads((FIXTURES_DIR / "yummy_bleach.json").read_text(encoding="utf-8"))
BLEACH_ID = 17212
BLEACH_URL = "https://yummyani.me/catalog/item/blich-tysyacheletnyaya-krovavaya-voyna-bedstvie"


# --- Без сети и базы ---

async def test_voiceover_names_from_yummy(monkeypatch):
    async def catalog():
        return ["AniDUB", "RedHeadSound", "AniLiberty", "JAM CLUB"]

    monkeypatch.setattr(voiceovers.db, "get_all_voiceover_names", catalog)
    monkeypatch.setattr(voiceovers, "_catalog_names", (0.0, {}))
    raw = ["Озвучка Дубляж AniDUB", "Озвучка AniDUB Online", "Озвучка Red Head Sound", "Озвучка AniLibria", "Озвучка JAM",
           "Субтитры SubVost", "Озвучка Комната Диди", "Субтитры"]
    assert await voiceovers.canonical_names(raw) == {
        "Озвучка Дубляж AniDUB": "AniDUB",
        "Озвучка AniDUB Online": "AniDUB",
        "Озвучка Red Head Sound": "RedHeadSound",
        "Озвучка AniLibria": "AniLiberty",
        "Озвучка JAM": "JAM CLUB",
        "Субтитры SubVost": "SubVost.Subtitles",
        "Озвучка Комната Диди": "Комната Диди",
        "Субтитры": "Субтитры",
    }
    assert voiceovers.matches("RedHeadSound", "Red Head Sound") and voiceovers.matches("Kazoku Project", "Kazoku Project.Subtitles")
    assert not voiceovers.matches("AniDUB", "AniStar")


def test_parsing_api_data():
    row = yummy.title_row(DATA["anime"])
    assert (row["id"], row["url"], row["shikimori_id"], row["status"], row["episodes_count"], row["episodes_aired"]) == (
        BLEACH_ID, BLEACH_URL, 60636, "ongoing", 10, 8,
    )
    assert row["next_episode_at"] == dt.datetime(2026, 9, 19, 14, 0) and row["poster_url"].startswith("https://static.yani.tv/")
    assert yummy.rule_info(row) == {"type": "Сериал", "status": "ongoing", "total_episodes": 10}
    assert yummy.rule_info({**row, "kind": "Полнометражный фильм", "status": "released"})["type"] == "Фильм"

    assert [yummy.parse_episode(value) for value in ("8", " 12 ", "8.5", "1-2", "Фильм", None)] == [8, 12, None, None, None, None]
    assert yummy.parse_payload("y17212") == BLEACH_ID and yummy.parse_payload("a17212") is None

    episodes = yummy.voiced_episodes(DATA["videos"])
    assert set(episodes) >= {"Озвучка AniDUB", "Озвучка Дубляж AniDUB", "Субтитры SubVost"}
    # Одна серия в двух плеерах — берётся самая ранняя загрузка
    kodik = [v for v in DATA["videos"] if v["data"]["dubbing"] == "Озвучка AniStar" and v["number"] == "1"]
    assert episodes["Озвучка AniStar"][1] == min(yummy.timestamp(v["date"]) for v in kodik)


# --- С базой и локальным «YummyAnime» ---

@pytest.fixture
async def fake_yummy(monkeypatch):
    state = {"anime": copy.deepcopy(DATA["anime"]), "videos": copy.deepcopy(DATA["videos"]), "feed": copy.deepcopy(DATA["feed_new_videos"]),
             "search": copy.deepcopy(DATA["search"]), "fail": False, "requests": []}

    async def handle(request):
        state["requests"].append(request.path)
        if state["fail"]:
            return web.Response(status=503, text="down")
        path = request.path
        if path == "/search":
            return web.json_response({"response": state["search"]})
        if path == "/feed":
            return web.json_response({"response": {"new_videos": state["feed"]}})
        if path == f"/anime/{BLEACH_ID}/videos":
            return web.json_response({"response": state["videos"]})
        if path == f"/anime/{BLEACH_ID}":
            return web.json_response({"response": state["anime"]})
        return web.json_response({"error": "Not found."}, status=404)

    app = web.Application()
    app.router.add_get("/{tail:.*}", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    monkeypatch.setattr(config, "YUMMY_API_URL", f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}")
    monkeypatch.setattr(config, "YUMMY_ENABLED", True)
    monkeypatch.setattr(yummy, "REQUEST_INTERVAL", 0)
    monkeypatch.setattr(yummy, "MAX_ATTEMPTS", 1)
    monkeypatch.setattr(yummy_sync, "_details_cache", {})
    monkeypatch.setattr(yummy_sync, "_feed_cache", (0.0, []))
    monkeypatch.setattr(yummy_sync, "_failed_cycles", 0)
    monkeypatch.setattr(yummy_sync, "_alerted", False)
    monkeypatch.setattr(voiceovers, "_catalog_names", (0.0, {}))
    yield state
    await runner.cleanup()


def add_episode(state, dubbing, number, hours_ago=0.1):
    uploaded = int((dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).timestamp())
    state["videos"].append({"video_id": 10 ** 7 + len(state["videos"]), "data": {"player": "Плеер Kodik", "dubbing": dubbing, "player_id": 4},
                            "number": str(number), "date": uploaded})


async def get_subscriptions(database):
    async with database.async_session() as session:
        return (await session.execute(select(Subscription))).scalars().all()


async def test_miniapp_search_details_and_subscribe(database, fake_yummy, client):
    await database.touch_voiceovers(["AniDUB", "RedHeadSound"])
    headers = init_data(60)

    found = (await client.get("/api/miniapp/yummy/search", params={"q": "Блич"}, headers=headers)).json()["items"]
    assert found[0]["id"] == BLEACH_ID and found[0]["url"] == BLEACH_URL
    assert (await client.get("/api/miniapp/yummy/search", params={"q": "Б"}, headers=headers)).status_code == 400

    details = (await client.get(f"/api/miniapp/yummy/anime/{BLEACH_ID}", headers=headers)).json()
    names = {dub["name"]: dub["last_episode"] for dub in details["voiceovers"]}
    # «AniDUB» и «Дубляж AniDUB» из разных плееров — одна озвучка; «Red Head Sound» сведён к справочнику
    assert names == {"AniStar": 8, "SubVost.Subtitles": 8, "AniDUB": 7, "RedHeadSound": 7}
    assert details["total_episodes"] == 10 and details["next_episode_at"] == "2026-09-19T14:00:00Z"
    assert (await client.get("/api/miniapp/yummy/anime/5", headers=headers)).status_code == 404

    created = await client.post("/api/miniapp/subscriptions", headers=headers, json={
        "source": "yummy", "source_id": str(BLEACH_ID), "voiceover": "anidub", "title": "подменённое название",
    })
    assert created.json() == {"ok": True, "created": True}
    sub = (await get_subscriptions(database))[0]
    assert (sub.source, sub.source_id, sub.anime_url, sub.anime_title, sub.voiceover, sub.last_episode, sub.total_episodes) == (
        "yummy", str(BLEACH_ID), BLEACH_URL, "Блич: Тысячелетняя кровавая война — Бедствие", "AniDUB", "Серия 7", 10,
    )
    listed = (await client.get("/api/miniapp/subscriptions", headers=headers)).json()["items"]
    assert listed[0]["source"] == "yummy" and listed[0]["source_id"] == str(BLEACH_ID)

    unknown = await client.post("/api/miniapp/subscriptions", headers=headers, json={"source": "yummy", "source_id": str(BLEACH_ID), "voiceover": "Нет такой"})
    assert unknown.status_code == 400 and "нет такой озвучки" in unknown.json()["detail"]

    fake_yummy["anime"]["type"] = {"name": "Полнометражный фильм", "alias": "movie"}
    yummy_sync._details_cache.clear()
    movie = await client.post("/api/miniapp/subscriptions", headers=headers, json={"source": "yummy", "source_id": str(BLEACH_ID), "voiceover": "AniStar"})
    assert movie.status_code == 400 and "фильм" in movie.json()["detail"]

    fake_yummy["fail"] = True
    yummy_sync._details_cache.clear()
    down = await client.post("/api/miniapp/subscriptions", headers=headers, json={"source": "yummy", "source_id": str(BLEACH_ID), "voiceover": "AniStar"})
    assert down.status_code == 502


async def test_yummy_feed_in_updates(database, fake_yummy, client):
    await database.touch_voiceovers(["AniDUB", "AniLiberty"])
    data = (await client.get("/api/miniapp/updates", params={"source": "yummy", "voiceover": "Все"}, headers=init_data(61))).json()
    assert data["source"] == "yummy"
    studios = [item["studio"] for item in data["items"]]
    assert "AniDUB" in studios and "AniLiberty" in studios and not any(studio.startswith("Озвучка") for studio in studios)
    assert all(item["source"] == "yummy" and item["link"].startswith("https://yummyani.me/catalog/item/") for item in data["items"])

    fake_yummy["fail"] = True
    yummy_sync._feed_cache = (0.0, [])
    assert (await client.get("/api/miniapp/updates", params={"source": "yummy"}, headers=init_data(61))).status_code == 502


async def test_new_episode_notification_and_title_refresh(database, fake_yummy, fake_bot, monkeypatch):
    await database.touch_voiceovers(["AniDUB"])
    await database.add_user(1, "u1")
    created, _, _ = await yummy_sync.subscribe(1, BLEACH_ID, "AniDUB")
    assert created

    # Ничего нового — уведомлений нет
    await yummy_sync.check_updates(fake_bot)
    assert fake_bot.texts_for(1) == []

    add_episode(fake_yummy, "Озвучка Дубляж AniDUB", 8)
    add_episode(fake_yummy, "Озвучка AniStar", 9)  # другая озвучка — не наша
    monkeypatch.setattr(yummy_sync, "TITLE_REFRESH", dt.timedelta(0))
    fake_yummy["anime"]["episodes"] = {"count": 12, "aired": 9, "next_date": int((dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=3)).timestamp())}
    counts = await yummy_sync.check_updates(fake_bot)

    assert counts == {"titles": 1, "failed": 0}
    [message] = fake_bot.texts_for(1)
    assert "Серия:</b> 8 из 12" in message and "AniDUB" in message and BLEACH_URL in message
    sub = (await get_subscriptions(database))[0]
    assert sub.last_episode == "Серия 8" and sub.total_episodes == 12
    async with database.async_session() as session:
        airing = await session.get(EpisodeAiring, (BLEACH_URL, 10))
    assert airing is not None and airing.source == "yummy"

    # AnimeGO-проверка подписки YummyAnime не трогает, даже если в истории есть новая серия
    add_episode(fake_yummy, "Озвучка AniDUB", 9)
    await database.record_episode_releases([
        {"anime_url": BLEACH_URL, "anime_title": "Блич", "studio": "AniDUB", "episode": 9, "released_at": dt.datetime.utcnow()},
    ])
    monkeypatch.setattr(parser, "get_home", feed(("Другое", "Серия 1", "AniDUB", "https://animego.me/anime/other-1")))
    await checker.check_updates(fake_bot)
    assert len(fake_bot.texts_for(1)) == 1


async def test_status_check_uses_yummy_api(database, fake_yummy, fake_bot, monkeypatch):
    fake_yummy["anime"]["anime_status"] = {"alias": "released", "title": "вышел"}
    fake_yummy["anime"]["episodes"] = {"count": 10, "aired": 10, "next_date": 0}
    sub_id = await add_sub(database, 1, "Блич", BLEACH_URL, "AniDUB", "Серия 10", checked_days_ago=10)
    async with database.async_session() as session:
        sub = await session.get(Subscription, sub_id)
        sub.source, sub.source_id = "yummy", str(BLEACH_ID)
        await session.commit()

    async def no_animego_pages(url, bot):
        raise AssertionError(f"AnimeGO page requested for {url}")

    monkeypatch.setattr(parser, "get_anime_info", no_animego_pages)
    counts = await checker.check_subscriptions_status(fake_bot)
    assert counts["yummy_urls"] == 1 and counts["completed"] == 1 and counts["checked_urls"] == 0
    assert await get_sub(database, sub_id) is None


async def test_unavailable_yummy_alerts_admins_once(database, fake_yummy, fake_bot):
    await database.touch_voiceovers(["AniDUB"])
    await database.add_user(1, "u1")
    await yummy_sync.subscribe(1, BLEACH_ID, "AniDUB")
    fake_yummy["fail"] = True
    for _ in range(yummy_sync.FAILURE_ALERT_CYCLES + 2):
        await yummy_sync.check_updates(fake_bot)
    alerts = fake_bot.texts_for(ADMIN_ID)
    assert len(alerts) == 1 and "YummyAnime не отвечает" in alerts[0]

    fake_yummy["fail"] = False
    await yummy_sync.check_updates(fake_bot)
    assert "снова отвечает" in fake_bot.texts_for(ADMIN_ID)[-1]


async def test_bot_find_and_deep_link(database, fake_yummy, telegram):
    session, send, press = telegram
    await database.touch_voiceovers(["AniDUB"])

    await send("/find Блич")
    results = session.last(EditMessageText)
    assert "YummyAnime" in results.text and buttons(results)[0].callback_data == f"yt:{BLEACH_ID}"

    await press(f"yt:{BLEACH_ID}")
    card = session.last(EditMessageText)
    assert "серий: 8 / 10" in card.text
    dubs = [item.text for item in buttons(card)][:4]
    # Сначала озвучки, дальше всех ушедшие по сериям; два написания Red Head Sound — одна озвучка
    assert dubs[:2] == ["AniStar · 8", "SubVost.Subtitles · 8"] and set(dubs[2:]) == {"AniDUB · 7", "Red Head Sound · 7"}
    assert button(card, "🔗 Открыть на YummyAnime").url == BLEACH_URL

    await press(button(card, "AniDUB · 7").callback_data)
    assert "Подписка оформлена" in session.last(EditMessageText).text
    await press(button(card, "AniDUB · 7").callback_data)
    assert session.last(AnswerCallbackQuery).text == "⚠️ Вы уже подписаны на эту озвучку"

    await press("my_subs")
    assert "YummyAnime" in session.last(EditMessageText).text

    await send(f"/start y{BLEACH_ID}")
    assert "AniStar · 8" in [item.text for item in buttons(session.last(EditMessageText))]
    await send("/start y5")
    assert "нет" in session.last(EditMessageText).text

    # Поиск без текста: бот ждёт название следующим сообщением
    await send("/find")
    assert "Напишите название" in session.last(SendMessage).text
    await send("Блич")
    assert buttons(session.last(EditMessageText))[0].callback_data == f"yt:{BLEACH_ID}"
