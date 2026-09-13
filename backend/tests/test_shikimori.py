"""Shikimori: сопоставление тайтлов, синхронизация, проверка подписок и админка."""
import datetime as dt
import json
from types import SimpleNamespace

import pytest
from aiohttp import web
from bs4 import BeautifulSoup
from sqlalchemy import select

import config
from conftest import ADMIN_ID, FIXTURES_DIR
from database.models import EpisodeAiring
from services import anime_titles, checker, parser, shikimori, shikimori_match, shikimori_sync
from test_db_flows import add_sub, client, get_sub, init_data  # noqa: F401 — фикстура client

BLEACH_URL = "https://animego.me/anime/blich-tysyacheletnyaya-krovavaya-voina-bedstviye-3590"
BLEACH_SEARCH = json.loads((FIXTURES_DIR / "shikimori_search_bleach.json").read_text(encoding="utf-8"))
BLEACH_META = shikimori_match.TitleMeta(
    russian="Блич: Тысячелетняя кровавая война — Бедствие",
    alt_names=["Блич: Тысячелетняя кровавая война 5 сезон"],
    english="Bleach: Thousand-Year Blood War - The Calamity",
    kind="Сериал",
    aired_on=dt.date(2026, 7, 25),
    episodes=10,
)


def anime(id_, russian, kind="tv", date="2011-10-02", episodes=12, name=None, **extra):
    return {"id": str(id_), "name": name or f"name {id_}", "russian": russian, "english": None, "japanese": None,
            "synonyms": [], "kind": kind, "status": "released", "episodes": episodes, "episodesAired": episodes,
            "airedOn": {"date": date}, "releasedOn": {"date": None}, "nextEpisodeAt": None,
            "url": f"https://shikimori.io/animes/{id_}", **extra}


# --- Сопоставление без сети ---

def test_normalize():
    assert shikimori_match.normalize("Блич: Тысячелетняя кровавая война — Бедствие") == "блич тысячелетняя кровавая война бедствие"
    assert shikimori_match.normalize("Ёлки-палки!") == shikimori_match.normalize("елки палки")
    assert shikimori_match.normalize("Hunter × Hunter") == "hunter x hunter"


def test_real_search_result_is_matched():
    result = shikimori_match.choose(BLEACH_META, BLEACH_SEARCH)
    assert result.status == "matched" and result.shikimori_id == 60636
    assert result.candidates[0]["russian"] == BLEACH_META.russian and result.candidates[0]["year"] == 2026
    # Только русское название, без данных со страницы — всё равно однозначно
    assert shikimori_match.choose(shikimori_match.TitleMeta(russian=BLEACH_META.russian), BLEACH_SEARCH).shikimori_id == 60636


def test_same_name_needs_year_or_admin():
    candidates = [anime(1, "Охотник х Охотник", date="1999-10-16", episodes=62), anime(2, "Охотник х Охотник", date="2011-10-02", episodes=148)]
    no_year = shikimori_match.choose(shikimori_match.TitleMeta(russian="Охотник х Охотник"), candidates)
    assert no_year.status == "ambiguous" and {item["id"] for item in no_year.candidates} == {1, 2}

    with_year = shikimori_match.choose(shikimori_match.TitleMeta(russian="Охотник х Охотник", aired_on=dt.date(2011, 10, 2)), candidates)
    assert with_year.status == "matched" and with_year.shikimori_id == 2


def test_kind_and_names():
    candidates = [anime(10, "Ван-Пис", kind="tv", date="1999-10-20"), anime(11, "Ван-Пис", kind="movie", date="2000-03-04")]
    movie = shikimori_match.choose(shikimori_match.TitleMeta(russian="Ван-Пис", kind="Фильм"), candidates)
    assert movie.status == "matched" and movie.shikimori_id == 11

    # Совпало только английское название — одного этого мало, решает админ
    english_only = [anime(20, "Другой перевод", english="Frieren")]
    result = shikimori_match.choose(shikimori_match.TitleMeta(russian="Фрирен", english="Frieren"), english_only)
    assert result.status == "ambiguous" and result.candidates[0]["id"] == 20
    # ...но вместе с годом и типом — достаточно
    result = shikimori_match.choose(
        shikimori_match.TitleMeta(russian="Фрирен", english="Frieren", kind="Сериал", aired_on=dt.date(2011, 1, 1)), english_only,
    )
    assert result.status == "matched"

    assert shikimori_match.choose(shikimori_match.TitleMeta(russian="Нет такого"), BLEACH_SEARCH).status == "not_found"
    assert shikimori_match.choose(shikimori_match.TitleMeta(russian="Нет такого"), []).status == "not_found"


def test_parse_title_page(fixture_html):
    meta = parser.parse_title_meta(BeautifulSoup(fixture_html("animego_title_bleach.html"), "html.parser"))
    assert meta["title"] == BLEACH_META.russian and meta["alt_names"] == BLEACH_META.alt_names
    assert (meta["english_title"], meta["kind"], meta["aired_on"], meta["episodes"]) == (
        BLEACH_META.english, "Сериал", dt.date(2026, 7, 25), 10,
    )
    assert shikimori_match.TitleMeta(russian=meta["title"], english=meta["english_title"]).search_queries() == [BLEACH_META.russian, BLEACH_META.english]
    # Страница без JSON-LD и синонимов
    empty = parser.parse_title_meta(BeautifulSoup("<h1>Название</h1>", "html.parser"))
    assert empty == {"title": "Название", "alt_names": [], "english_title": None, "kind": None, "aired_on": None, "episodes": None, "poster_url": None}


def test_client_helpers():
    assert shikimori.parse_id("52991") == 52991
    assert shikimori.parse_id("https://shikimori.io/animes/z52991-sousou-no-frieren") == 52991
    assert shikimori.parse_id("https://shikimori.one/animes/60636-bleach") == 60636
    assert shikimori.parse_id("frieren") is None and shikimori.parse_id(0) is None
    row = shikimori.to_row(BLEACH_SEARCH[0])
    assert row["next_episode_at"] == dt.datetime(2026, 9, 19, 14, 0) and row["aired_on"] == dt.date(2026, 7, 25)


# --- Решения по данным Shikimori ---

NOW = dt.datetime(2026, 9, 14, 12, 0)


def title_with(status="released", episodes=12, episodes_aired=12, synced_hours_ago=1, match="matched", animego_episodes=None,
               next_episode_at=None):
    anime_row = SimpleNamespace(status=status, episodes=episodes, episodes_aired=episodes_aired, next_episode_at=next_episode_at,
                                synced_at=NOW - dt.timedelta(hours=synced_hours_ago))
    return SimpleNamespace(shikimori_status=match, shikimori=anime_row, episodes=animego_episodes, url="u")


def subs(*pairs):
    return [SimpleNamespace(last_episode=last, total_episodes=total) for last, total in pairs]


def test_status_from_shikimori_guards():
    decide = shikimori_sync.status_from_shikimori
    assert decide(title_with(), subs(("Серия 5", None)), NOW) == {"total_episodes": 12, "released": True}
    # Не сопоставлен, данные устарели, статус неизвестен
    assert decide(title_with(match="not_found"), subs(("Серия 5", None)), NOW) is None
    assert decide(title_with(synced_hours_ago=72), subs(("Серия 5", None)), NOW) is None
    assert decide(None, subs(("Серия 5", None)), NOW) is None
    # Сквозная нумерация на AnimeGO: серия 14 при 12 сериях на Shikimori
    assert decide(title_with(), subs(("Серия 14", None)), NOW) is None
    # AnimeGO уже знает другое число серий
    assert decide(title_with(), subs(("Серия 5", 13)), NOW) is None
    # Онгоинг: число серий берём, только если оно совпадает с AnimeGO
    assert decide(title_with(status="ongoing", episodes_aired=8), subs(("Серия 7", None)), NOW) == {"total_episodes": None, "released": False}
    assert decide(title_with(status="ongoing", animego_episodes=12), subs(("Серия 7", None)), NOW) == {"total_episodes": 12, "released": False}
    # Вышел, но число серий неизвестно — нужна страница
    assert decide(title_with(episodes=0), subs(("Серия 7", None)), NOW) is None


def test_airing_row_guards():
    title = SimpleNamespace(url="u")
    future = NOW + dt.timedelta(days=2)
    ongoing = SimpleNamespace(next_episode_at=future, episodes_aired=8)
    assert shikimori_sync.airing_row(title, ongoing, 7, NOW) == {"anime_url": "u", "episode": 9, "air_at": future}
    assert shikimori_sync.airing_row(title, ongoing, None, NOW)["episode"] == 9
    assert shikimori_sync.airing_row(title, ongoing, 20, NOW) is None  # нумерация AnimeGO ушла вперёд оригинала
    assert shikimori_sync.airing_row(title, SimpleNamespace(next_episode_at=NOW - dt.timedelta(hours=1), episodes_aired=8), 7, NOW) is None


def test_match_due():
    def title(status, checked_days_ago=None, meta_days_ago=None):
        return SimpleNamespace(
            shikimori_status=status,
            shikimori_checked_at=None if checked_days_ago is None else NOW - dt.timedelta(days=checked_days_ago),
            meta_updated_at=None if meta_days_ago is None else NOW - dt.timedelta(days=meta_days_ago),
        )

    assert shikimori_sync.match_due(title("pending"), NOW)
    assert not shikimori_sync.match_due(title("not_found", 2), NOW)
    assert shikimori_sync.match_due(title("not_found", 8), NOW)
    assert shikimori_sync.match_due(title("ambiguous", 2, meta_days_ago=1), NOW)  # страница AnimeGO обновилась
    assert not shikimori_sync.match_due(title("error", 1 / 48), NOW) and shikimori_sync.match_due(title("error", 1 / 12), NOW)
    for status in ("matched", "manual", "absent"):
        assert not shikimori_sync.match_due(title(status, 30), NOW)


# --- С базой и локальным «Shikimori» ---

@pytest.fixture
async def fake_shikimori(monkeypatch):
    """GraphQL Shikimori на локальном сервере: поиск по словарю, ids — по каталогу"""
    state = {"search": {}, "catalog": {}, "fail": False, "requests": []}

    async def graphql(request):
        body = await request.json()
        state["requests"].append(body["variables"])
        if state["fail"]:
            return web.Response(status=503, text="unavailable")
        variables = body["variables"]
        if "search" in variables:
            found = state["search"].get(variables["search"], [])
        else:
            found = [state["catalog"][id_] for id_ in variables["ids"].split(",") if id_ in state["catalog"]]
        return web.json_response({"data": {"animes": found}})

    app = web.Application()
    app.router.add_post("/api/graphql", graphql)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    monkeypatch.setattr(config, "SHIKIMORI_URL", f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}")
    monkeypatch.setattr(config, "SHIKIMORI_ENABLED", True)
    monkeypatch.setattr(shikimori, "REQUEST_INTERVAL", 0)
    monkeypatch.setattr(shikimori, "MAX_ATTEMPTS", 1)
    yield state
    await runner.cleanup()


async def test_title_page_meta_is_saved_once(database, fixture_html, monkeypatch):
    async def fake_html(url, session=None, bot=None):
        return fixture_html("animego_title_bleach.html")

    monkeypatch.setattr(parser, "get_html", fake_html)
    details = await parser.get_anime_details(BLEACH_URL, None)
    assert details["total_episodes"] == 10 and "AniDUB" in details["available_voiceovers"]

    title = await database.get_anime_title(3590)
    assert (title.title, title.english_title, title.kind, title.aired_on, title.episodes) == (
        BLEACH_META.russian, BLEACH_META.english, "Сериал", dt.date(2026, 7, 25), 10,
    )
    first_meta_update = title.meta_updated_at
    await parser.get_anime_info(BLEACH_URL, None)
    assert (await database.get_anime_title(3590)).meta_updated_at == first_meta_update  # данные не поменялись


async def test_sync_matches_refreshes_and_records_airings(database, fake_shikimori):
    now = dt.datetime.utcnow()
    next_at = (now + dt.timedelta(days=3)).replace(microsecond=0)
    bleach = {**BLEACH_SEARCH[0], "nextEpisodeAt": next_at.isoformat() + "+00:00"}
    fake_shikimori["search"] = {BLEACH_META.russian: [bleach, *BLEACH_SEARCH[1:]], BLEACH_META.english: [bleach]}
    fake_shikimori["catalog"] = {"60636": bleach}

    await anime_titles.remember_meta(BLEACH_URL, {
        "title": BLEACH_META.russian, "alt_names": BLEACH_META.alt_names, "english_title": BLEACH_META.english,
        "kind": "Сериал", "aired_on": dt.date(2026, 7, 25), "episodes": 10,
    })
    await anime_titles.remember([{"title": "Хеллсинг", "link": "https://animego.me/anime/hellsing-11"}])
    await anime_titles.remember([{"title": "Без подписки", "link": "https://animego.me/anime/nobody-12"}])
    await add_sub(database, 1, "Блич", BLEACH_URL, "AniDUB", "Серия 7")
    await add_sub(database, 1, "Хеллсинг", "https://animego.me/anime/hellsing-11", "AniDUB", "Серия 1")
    # Время из расписания AnimeGO уже есть для 8-й серии, Shikimori его не трогает
    await database.record_episode_airings([{"anime_url": BLEACH_URL, "episode": 9, "air_at": now + dt.timedelta(days=4)}])

    counts = await shikimori_sync.sync()
    assert counts["titles"] == 2 and counts["matched"] == 1 and counts["not_found"] == 1
    assert {request.get("search") for request in fake_shikimori["requests"]} >= {BLEACH_META.russian, "Хеллсинг"}

    bleach_title = await database.get_anime_title(3590)
    assert bleach_title.shikimori_status == "matched" and bleach_title.shikimori.episodes_aired == 8
    assert (await database.get_anime_title(11)).shikimori_status == "not_found"
    assert (await database.get_anime_title(12)).shikimori_status == "pending"  # без подписок не ищем

    async with database.async_session() as session:
        airing = await session.get(EpisodeAiring, (BLEACH_URL, 9))
    assert airing.source == "animego" and airing.air_at != next_at  # AnimeGO главнее

    # AnimeGO убрал серию из расписания — Shikimori записывает своё время; повторный sync ничего не ищет заново
    async with database.async_session() as session:
        await session.delete(await session.get(EpisodeAiring, (BLEACH_URL, 9)))
        await session.commit()
    fake_shikimori["requests"].clear()
    counts = await shikimori_sync.sync()
    assert counts["matched"] == counts["not_found"] == 0 and not any("search" in request for request in fake_shikimori["requests"])
    async with database.async_session() as session:
        airing = await session.get(EpisodeAiring, (BLEACH_URL, 9))
    assert airing.source == "shikimori" and airing.air_at == next_at

    # Расписание AnimeGO перезаписывает время Shikimori
    await database.record_episode_airings([{"anime_url": BLEACH_URL, "episode": 9, "air_at": next_at + dt.timedelta(hours=1)}])
    async with database.async_session() as session:
        airing = await session.get(EpisodeAiring, (BLEACH_URL, 9))
    assert airing.source == "animego"


async def test_shikimori_unavailable_keeps_animego_flow(database, fake_shikimori, fake_bot, monkeypatch):
    fake_shikimori["fail"] = True
    await anime_titles.remember([{"title": "Тайтл", "link": "https://animego.me/anime/title-5"}])
    sub_id = await add_sub(database, 1, "Тайтл", "https://animego.me/anime/title-5", "AniDUB", "Серия 3", checked_days_ago=10)

    counts = await shikimori_sync.sync()
    assert counts["error"] == 1
    title = await database.get_anime_title(5)
    assert title.shikimori_status == "error" and "503" in title.shikimori_error

    pages = []

    async def fake_info(url, bot):
        pages.append(url)
        return {"type": "Сериал", "status": "Онгоинг", "total_episodes": 12}

    monkeypatch.setattr(parser, "get_anime_info", fake_info)
    await checker.check_subscriptions_status(fake_bot)
    assert pages == ["https://animego.me/anime/title-5"] and (await get_sub(database, sub_id)).total_episodes == 12


async def test_status_check_uses_shikimori_instead_of_page(database, fake_shikimori, fake_bot, monkeypatch):
    url = "https://animego.me/anime/finished-7"
    fake_shikimori["search"] = {"Законченный": [anime(700, "Законченный", episodes=12)]}
    await anime_titles.remember([{"title": "Законченный", "link": url}])
    done = await add_sub(database, 1, "Законченный", url, "AniDUB", "Серия 12", checked_days_ago=10)
    await shikimori_sync.sync()

    offset_url = "https://animego.me/anime/second-season-8"
    fake_shikimori["search"]["Второй сезон"] = [anime(800, "Второй сезон", episodes=12)]
    await anime_titles.remember([{"title": "Второй сезон", "link": offset_url}])
    offset = await add_sub(database, 1, "Второй сезон", offset_url, "AniDUB", "Серия 14", checked_days_ago=10)
    await shikimori_sync.sync()

    pages = []

    async def fake_info(url_, bot):
        pages.append(url_)
        return {"type": "Сериал", "status": "Онгоинг", "total_episodes": 24}

    monkeypatch.setattr(parser, "get_anime_info", fake_info)
    counts = await checker.check_subscriptions_status(fake_bot)

    assert counts["shikimori_urls"] == 1 and counts["completed"] == 1
    assert await get_sub(database, done) is None and "завершено" in fake_bot.texts_for(1)[0]
    # Нумерация AnimeGO не сходится с Shikimori — смотрим страницу и не снимаем подписку
    assert pages == [offset_url] and (await get_sub(database, offset)).total_episodes == 24


async def test_admin_shikimori_api(database, fake_shikimori, client):
    headers = init_data(ADMIN_ID)
    fake_shikimori["search"] = {"Охотник х Охотник": [anime(1, "Охотник х Охотник", date="1999-10-16"), anime(2, "Охотник х Охотник")]}
    fake_shikimori["catalog"] = {"2": anime(2, "Охотник х Охотник"), "11": anime(11, "Хеллсинг: Война с нечистью")}
    await anime_titles.remember([{"title": "Охотник х Охотник", "link": "https://animego.me/anime/hxh-21"}])
    await anime_titles.remember([{"title": "Хеллсинг", "link": "https://animego.me/anime/hellsing-22"}])
    await anime_titles.remember([{"title": "Готовый", "link": "https://animego.me/anime/ready-23"}])
    for url in ("https://animego.me/anime/hxh-21", "https://animego.me/anime/hellsing-22", "https://animego.me/anime/ready-23"):
        await add_sub(database, 1, "T", url, "AniDUB", "Серия 1")
    await shikimori_sync.sync()

    overview = (await client.get("/api/miniapp/admin/shikimori", headers=headers)).json()
    assert [title["status"] for title in overview["titles"]] == ["ambiguous", "not_found", "not_found"]
    assert overview["summary"]["ambiguous"] == 1 and len(overview["titles"][0]["candidates"]) == 2
    assert (await client.get("/api/miniapp/admin/shikimori", headers=init_data(5))).status_code == 403

    picked = await client.put("/api/miniapp/admin/shikimori/21", headers=headers, json={"shikimori": "https://shikimori.io/animes/2-hunter"})
    hxh = next(title for title in picked.json()["titles"] if title["id"] == 21)
    assert hxh["status"] == "manual" and hxh["shikimori"]["id"] == 2 and len(hxh["candidates"]) == 2

    missing = await client.put("/api/miniapp/admin/shikimori/22", headers=headers, json={"shikimori": 999})
    assert missing.status_code == 404 and "999" in missing.json()["detail"]
    bad = await client.put("/api/miniapp/admin/shikimori/22", headers=headers, json={"shikimori": "hellsing"})
    assert bad.status_code == 400

    absent = await client.put("/api/miniapp/admin/shikimori/23", headers=headers, json={"absent": True})
    assert next(title for title in absent.json()["titles"] if title["id"] == 23)["status"] == "absent"
    await shikimori_sync.sync(force=True)
    assert (await database.get_anime_title(23)).shikimori_status == "absent"  # решение админа не перетирается
    assert (await database.get_anime_title(21)).shikimori_status == "manual"

    fake_shikimori["search"]["Хеллсинг"] = [anime(11, "Хеллсинг")]
    rechecked = await client.put("/api/miniapp/admin/shikimori/22", headers=headers, json={"recheck": True})
    assert next(title for title in rechecked.json()["titles"] if title["id"] == 22)["status"] == "matched"
    assert (await client.put("/api/miniapp/admin/shikimori/404", headers=headers, json={"absent": True})).status_code == 404
