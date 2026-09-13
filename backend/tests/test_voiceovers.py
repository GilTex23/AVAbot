"""Справочник озвучек, любимые озвучки и фильтр ленты."""
import datetime as dt

from bs4 import BeautifulSoup

from keyboards import inline
from services import forecast, parser, voiceovers
from test_db_flows import add_sub, client, feed, init_data  # noqa: F401 — фикстура client

UPDATES = [
    {"title": "A", "episode": "Серия 1", "studio": "AniLiberty", "link": "a"},
    {"title": "B", "episode": "Серия 2", "studio": "Kazoku Project.Subtitles", "link": "b"},
    {"title": "C", "episode": "Серия 3", "studio": "AniDUB", "link": "c"},
    {"title": "D", "episode": "Серия 4", "studio": "AniLiberty", "link": "d"},
]


def test_filter_updates():
    assert voiceovers.filter_updates(UPDATES, []) == UPDATES
    assert [item["link"] for item in voiceovers.filter_updates(UPDATES, ["aniliberty"])] == ["a", "d"]
    # Озвучка входит в название студии — так же, как для подписок
    assert [item["link"] for item in voiceovers.filter_updates(UPDATES, ["Kazoku Project", "AniDUB"])] == ["b", "c"]
    assert voiceovers.studios_in(UPDATES) == [
        {"name": "AniLiberty", "count": 2}, {"name": "AniDUB", "count": 1}, {"name": "Kazoku Project.Subtitles", "count": 1},
    ]


def test_names_helpers():
    assert voiceovers.clean_names([" AniDUB ", "anidub", "", "Все", 5, "AniLiberty"]) == ["AniDUB", "AniLiberty"]
    assert voiceovers.describe([]) == "Все озвучки"
    assert voiceovers.describe(["A", "B", "C", "D", "E"]) == "A, B, C и ещё 2"
    assert forecast.voiceover_matches("Все", "что угодно")


def test_favorites_keyboard_fits_callback_limit():
    catalog = [{"id": 100000 + index, "name": f"Очень длинное название озвучки номер {index}"} for index in range(23)]
    markup = inline.favorite_voiceovers(catalog, [catalog[0]["name"], catalog[12]["name"]], page=1, context=inline.FAVORITES_SETTINGS)
    buttons = [button for row in markup.inline_keyboard for button in row]

    assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in buttons)
    names = [button.text for button in buttons if button.callback_data.startswith("fav:t:")]
    assert len(names) == inline.FAVORITES_PAGE_SIZE and names[2] == "✅ " + catalog[12]["name"]
    assert any(button.text == "2 / 3" for button in buttons)
    assert any(button.callback_data.startswith("fav:c:") for button in buttons)

    # Страница за пределами списка прижимается к последней
    last = inline.favorite_voiceovers(catalog, [], page=99, context=inline.FAVORITES_ONBOARDING)
    last_buttons = [button for row in last.inline_keyboard for button in row]
    assert sum(button.callback_data.startswith("fav:t:") for button in last_buttons) == 3
    assert last_buttons[-1].text == "✅ Готово" and not any(button.callback_data.startswith("fav:c:") for button in last_buttons)


async def test_catalog_is_filled_from_feed_and_title_pages(database, fixture_html, monkeypatch):
    soup = BeautifulSoup(fixture_html("animego_home_moscow.html"), "html.parser")
    zone = parser._page_zone(soup)
    # Время «сейчас»: популярность считается за последние POPULAR_DAYS дней
    home = {"updates": parser._parse_updates(soup, dt.datetime.now(dt.timezone.utc), zone), "schedule": []}
    await add_sub(database, 1, "T", "https://animego.me/anime/x", "AniLiberty", "Серия 1")
    await add_sub(database, 2, "T", "https://animego.me/anime/x", "AniLiberty", "Серия 1")

    await forecast.record_home(home, [])
    await voiceovers.remember(["Редкая студия", " ", "Все"])

    catalog = await voiceovers.catalog()
    names = [item["name"] for item in catalog]
    assert "Все" not in names and "Редкая студия" in names
    # Больше всего серий в ленте у MDA; дальше при равенстве серий — те, на что подписаны
    assert names[0] == "MDA"
    by_name = {item["name"]: item for item in catalog}
    assert by_name["AniLiberty"]["subscriptions"] == 2 and by_name["Редкая студия"]["releases"] == 0

    before = by_name["MDA"]["last_seen_at"]
    await database.touch_voiceovers(["MDA"], seen_at=before - dt.timedelta(days=1))
    assert {item["name"]: item for item in await voiceovers.catalog()}["MDA"]["last_seen_at"] == before


async def test_favorites_api_and_updates_filter(database, client, monkeypatch):
    await database.touch_voiceovers(["AniLiberty", "AniDUB", "Kazoku Project"])
    home = feed(
        ("A", "Серия 1", "AniLiberty", "https://animego.me/anime/a"),
        ("B", "Серия 2", "AniDUB", "https://animego.me/anime/b"),
        ("C", "Серия 3", "Kazoku Project.Subtitles", "https://animego.me/anime/c"),
    )

    async def fake_updates(bot):
        return (await home(bot))["updates"]

    monkeypatch.setattr(parser, "get_updates", fake_updates)
    headers = init_data(50)

    me = await client.get("/api/miniapp/me", headers=headers)
    assert me.json()["favorite_voiceovers"] == []
    everything = (await client.get("/api/miniapp/updates", headers=headers)).json()
    assert everything["filter"] == "favorites" and len(everything["items"]) == 3
    assert [studio["name"] for studio in everything["studios"]] == ["AniDUB", "AniLiberty", "Kazoku Project.Subtitles"]

    unknown = await client.put("/api/miniapp/settings/voiceovers", headers=headers, json={"voiceovers": ["AniLiberty", "Нет такой"]})
    assert unknown.status_code == 400 and "Нет такой" in unknown.json()["detail"]
    not_list = await client.put("/api/miniapp/settings/voiceovers", headers=headers, json={"voiceovers": "AniLiberty"})
    assert not_list.status_code == 400

    saved = await client.put("/api/miniapp/settings/voiceovers", headers=headers, json={"voiceovers": ["Kazoku Project", "AniLiberty", "aniliberty"]})
    assert saved.status_code == 200 and saved.json()["favorite_voiceovers"] == ["Kazoku Project", "AniLiberty"]
    assert await database.get_user_favorite_voiceovers(50) == ["Kazoku Project", "AniLiberty"]

    favorites = (await client.get("/api/miniapp/updates", headers=headers)).json()
    assert [item["title"] for item in favorites["items"]] == ["A", "C"] and favorites["favorites"] == ["Kazoku Project", "AniLiberty"]
    one = (await client.get("/api/miniapp/updates", params={"voiceover": "AniDUB"}, headers=headers)).json()
    assert one["filter"] == "voiceover" and [item["title"] for item in one["items"]] == ["B"]
    everything = (await client.get("/api/miniapp/updates", params={"voiceover": "Все"}, headers=headers)).json()
    assert everything["filter"] == "all" and len(everything["items"]) == 3

    catalog = (await client.get("/api/miniapp/voiceovers", headers=headers)).json()
    assert {item["name"] for item in catalog["items"]} == {"AniLiberty", "AniDUB", "Kazoku Project"}
    assert catalog["popular_days"] == voiceovers.POPULAR_DAYS

    cleared = await client.put("/api/miniapp/settings/voiceovers", headers=headers, json={"voiceovers": []})
    assert cleared.json()["favorite_voiceovers"] == []
