"""Оценки тайтлов с AnimeGO, Shikimori и YummyAnime."""
import copy
import datetime as dt
import json

from bs4 import BeautifulSoup
from sqlalchemy import update

from conftest import FIXTURES_DIR
from database.models import AnimeTitle, Subscription
from services import anime_titles, parser, ratings, shikimori, shikimori_sync, yummy
from test_db_flows import add_sub, client, init_data  # noqa: F401 — фикстура client
from test_shikimori import fake_shikimori  # noqa: F401 — фикстура fake_shikimori

YUMMY = json.loads((FIXTURES_DIR / "yummy_bleach.json").read_text(encoding="utf-8"))
ANIMEGO_URL = "https://animego.me/anime/blich-tysyacheletnyaya-krovavaya-voina-bedstviye-3590"
YUMMY_URL = "https://yummyani.me/catalog/item/blich-tysyacheletnyaya-krovavaya-voyna-bedstvie"


def test_parse_ratings(fixture_html):
    soup = BeautifulSoup(fixture_html("animego_title_bleach.html"), "html.parser")
    assert parser.parse_rating(soup) == (9.0, 872)
    meta = parser.parse_title_meta(soup)
    assert (meta["rating"], meta["rating_votes"]) == (9.0, 872)

    # Без блока рейтинга — из JSON-LD; без голосов оценки нет
    only_ld = BeautifulSoup("<h1>T</h1>", "html.parser")
    assert parser.parse_rating(only_ld, {"aggregateRating": {"ratingValue": 8, "ratingCount": 15}}) == (8.0, 15)
    assert parser.parse_rating(only_ld, {"aggregateRating": {"ratingValue": 0, "ratingCount": 0}}) == (None, None)
    assert parser.parse_rating(BeautifulSoup('<span class="entity-rating__value">7,35</span><div class="entity-rating__count">1 204</div>', "html.parser")) == (7.35, 1204)

    anime = copy.deepcopy(YUMMY["anime"])
    anime["rating"] = {"average": 9.29795396419441, "counters": 782, "shikimori_rating": 8.69}
    row = yummy.title_row(anime)
    assert (row["rating"], row["rating_votes"]) == (9.3, 782)
    assert yummy.title_row(YUMMY["anime"])["rating"] is None

    assert shikimori.to_row({"id": "1", "name": "A", "score": 9.05})["score"] == 9.05
    assert shikimori.to_row({"id": "2", "name": "B", "score": 0})["score"] is None  # анонс


def test_describe():
    items = [{"source": "animego", "value": 9.0}, {"source": "shikimori", "value": 9.05}, {"source": "yummy", "value": 9.3}]
    assert ratings.describe(items) == "⭐ AnimeGO 9 · Shikimori 9.05 · YummyAnime 9.3"
    assert ratings.describe([]) == ""


async def seed_linked_titles(database):
    """Тайтл есть на всех трёх сайтах и связан через id 60636 на Shikimori"""
    await anime_titles.remember_meta(ANIMEGO_URL, {"title": "Блич", "rating": 9.0, "rating_votes": 872})
    await database.upsert_shikimori_animes([{"id": 60636, "name": "Bleach", "score": 9.05, "url": "https://shikimori.io/animes/60636"}])
    await database.set_title_shikimori(3590, "matched", 60636)
    anime = copy.deepcopy(YUMMY["anime"])
    anime["rating"] = {"average": 9.3, "counters": 782}
    await database.upsert_yummy_titles([yummy.title_row(anime)])


async def test_ratings_for_subscriptions_across_sources(database, client, fixture_html, monkeypatch):
    await seed_linked_titles(database)
    animego_sub = await add_sub(database, 70, "Блич", ANIMEGO_URL, "AniDUB", "Серия 7")
    yummy_sub = await add_sub(database, 70, "Блич", YUMMY_URL, "AniStar", "Серия 8")
    lonely_sub = await add_sub(database, 70, "Без сопоставления", "https://animego.me/anime/lonely-11", "AniDUB", "Серия 1")
    async with database.async_session() as session:
        await session.execute(update(Subscription).where(Subscription.id == yummy_sub).values(source="yummy", source_id="17212"))
        await session.commit()
    await anime_titles.remember_meta("https://animego.me/anime/lonely-11", {"title": "Без сопоставления", "rating": 7.1, "rating_votes": 40})

    items = {item["id"]: item["ratings"] for item in (await client.get("/api/miniapp/subscriptions", headers=init_data(70))).json()["items"]}
    assert [(item["source"], item["value"]) for item in items[animego_sub]] == [("animego", 9.0), ("shikimori", 9.05), ("yummy", 9.3)]
    assert [(item["source"], item["value"]) for item in items[yummy_sub]] == [("animego", 9.0), ("shikimori", 9.05), ("yummy", 9.3)]
    assert items[lonely_sub] == [{"source": "animego", "value": 7.1, "votes": 40, "url": "https://animego.me/anime/lonely-11"}]

    week = (await client.get("/api/miniapp/my-week", headers=init_data(70))).json()["items"]
    assert all("ratings" in item for item in week)

    # Страница тайтла без блока рейтинга не стирает сохранённую оценку
    await anime_titles.remember_meta(ANIMEGO_URL, {"title": "Блич"})
    async with database.async_session() as session:
        assert (await session.get(AnimeTitle, 3590)).rating == 9.0

    async def fake_html(url, session=None, bot=None):
        return fixture_html("animego_title_bleach.html")

    monkeypatch.setattr(parser, "get_html", fake_html)
    details = (await client.get("/api/miniapp/anime-details", params={"link": ANIMEGO_URL}, headers=init_data(70))).json()
    assert [(item["source"], item["value"], item["votes"]) for item in details["ratings"]] == [
        ("animego", 9.0, 872), ("shikimori", 9.05, None), ("yummy", 9.3, 782),
    ]


async def test_shikimori_sync_refreshes_yummy_titles(database, fake_shikimori):
    anime = copy.deepcopy(YUMMY["anime"])
    await database.upsert_yummy_titles([yummy.title_row(anime)])
    sub_id = await add_sub(database, 71, "Блич", YUMMY_URL, "AniStar", "Серия 8")
    async with database.async_session() as session:
        await session.execute(update(Subscription).where(Subscription.id == sub_id).values(source="yummy", source_id="17212"))
        await session.commit()
    fake_shikimori["catalog"] = {"60636": {"id": "60636", "name": "Bleach", "russian": "Блич", "kind": "tv", "status": "ongoing",
                                           "episodes": 10, "episodesAired": 8, "score": 9.05, "url": "https://shikimori.io/animes/60636"}}

    counts = await shikimori_sync.sync()
    assert counts["refreshed"] == 1
    assert (await database.get_shikimori_animes({60636}))[60636].score == 9.05

    rating_items = (await ratings.for_subscriptions(await database.get_user_subscriptions(71)))[sub_id]
    assert [item["source"] for item in rating_items] == ["shikimori"]
    assert dt.datetime.utcnow() - (await database.get_shikimori_animes({60636}))[60636].synced_at < dt.timedelta(minutes=1)
