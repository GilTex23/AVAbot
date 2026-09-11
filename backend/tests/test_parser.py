import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from services import parser
from services.timezone_labels import TIMEZONE_LABELS

# Обе фикстуры загружены в одну минуту через разные прокси ScraperAPI
FETCHED_AT = dt.datetime(2026, 9, 11, 13, 49, tzinfo=parser.MSK)


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    zone = parser._page_zone(soup)
    return zone, parser._parse_updates(soup, FETCHED_AT, zone), parser._parse_schedule(soup, FETCHED_AT, zone)


def msk_date(utc_naive):
    return parser._utc_naive_to(utc_naive, parser.MSK).date()


@pytest.mark.parametrize("text, expected", [
    ("6 / 13", 13), ("11 / ?", None), ("11/?", None), ("14", 14), ("", None), (None, None), ("?", None),
])
def test_parse_total_episodes(text, expected):
    assert parser.parse_total_episodes(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Серия 11", [11]), ("Серии 11", [11]), ("Серии 1, 7-8", [1, 7, 8]), ("Серия 18 и 19 ", [18, 19]),
    ("Серии 3 - 5", [3, 4, 5]), ("Серия 6.5", []), ("Серия", []), (None, []),
])
def test_parse_episode_list(text, expected):
    assert parser.parse_episode_list(text) == expected


def test_max_episode_number():
    assert parser.max_episode_number("Серии 1, 7-8") == 8
    assert parser.max_episode_number("Серия 6.5") == 6.5
    assert parser.max_episode_number(None) == 0


def test_parse_day_around_new_year():
    late_december = dt.datetime(2026, 12, 30, 12, tzinfo=parser.MSK)
    early_january = dt.datetime(2027, 1, 2, 12, tzinfo=parser.MSK)
    assert parser._parse_day("2 января", late_december) == dt.date(2027, 1, 2)
    assert parser._parse_day("30 декабря", early_january) == dt.date(2026, 12, 30)
    assert parser._parse_day("5 мая 2025", early_january) == dt.date(2025, 5, 5)
    assert parser._parse_day("нечто", early_january) is None
    assert parser._parse_local_datetime("Вчера", "00:05", parser.MSK, early_january) == dt.datetime(2026, 12, 31, 21, 5)


def test_timezone_labels():
    assert TIMEZONE_LABELS["Москва"] == "Europe/Moscow"
    assert TIMEZONE_LABELS["Армения"] == "Asia/Yerevan"
    assert TIMEZONE_LABELS["Екатеринбург"] == "Asia/Yekaterinburg"
    # За подписью стоят пояса с разными смещениями (Калининград и Киев) — такой странице не доверяем
    assert "Восточная Европа" not in TIMEZONE_LABELS


def test_moscow_page_feed(fixture_html):
    zone, updates, _ = parse(fixture_html("animego_home_moscow.html"))
    assert str(zone) == "Europe/Moscow"
    assert len(updates) == 20 and all(update["released_at"] for update in updates)

    first = updates[0]
    assert (first["studio"], first["episode"]) == ("AniDUB", "Серии 11")
    assert first["released_at"] == dt.datetime(2026, 9, 11, 9, 50)  # «Сегодня, 12:50» по Москве
    assert "#" not in first["link"]
    assert max(update["released_at"] for update in updates) <= FETCHED_AT.astimezone(dt.timezone.utc).replace(tzinfo=None)

    batch = next(update for update in updates if update["studio"] == "MDA" and "7-8" in update["episode"])
    assert parser.parse_episode_list(batch["episode"]) == [1, 7, 8]


def test_moscow_page_schedule(fixture_html):
    _, _, schedule = parse(fixture_html("animego_home_moscow.html"))
    items = [item for day in schedule for item in day["items"]]

    assert len(schedule) == 7
    monday = schedule[0]
    assert monday["date_str"] == "Понедельник 14 сентября"
    assert monday["items"][0]["episodes"] == [11] and monday["items"][0]["total_episodes"] == 12
    assert monday["items"][0]["air_at"] == dt.datetime(2026, 9, 14, 11, 57)
    assert any(day["date_str"] == "Суббота" for day in schedule)  # «Завтра» в заголовке остаётся днём недели

    double = next(item for item in items if item["episodes"] == [18, 19])
    assert double["total_episodes"] == 56 and double["air_at"] is None  # у части тайтлов время не указано
    assert all(item["episodes"] for item in items)
    assert all(item["time"].endswith("(Москва)") for item in items if item["air_at"])


def test_proxy_timezone_does_not_change_result(fixture_html):
    zone_a, updates_a, schedule_a = parse(fixture_html("animego_home_armenia.html"))
    zone_m, updates_m, schedule_m = parse(fixture_html("animego_home_moscow.html"))
    assert str(zone_a) == "Asia/Yerevan"
    assert "(Армения)" in fixture_html("animego_home_armenia.html")

    feed_a = {(u["link"], u["studio"], u["episode"]): u["released_at"] for u in updates_a}
    feed_m = {(u["link"], u["studio"], u["episode"]): u["released_at"] for u in updates_m}
    assert feed_a == feed_m

    def days(schedule):
        return [(day["date_str"], [(item["link"], item["time"], item["air_at"]) for item in day["items"]]) for day in schedule]

    assert days(schedule_a) == days(schedule_m)


def test_far_east_proxy_regrouped_by_moscow_date(fixture_html):
    moscow_html = fixture_html("animego_home_moscow.html")
    _, _, schedule_m = parse(moscow_html)
    zone, _, schedule_v = parse(moscow_html.replace("(Москва)", "(Владивосток)"))
    assert str(zone) == "Asia/Vladivostok"

    for day in schedule_v:
        assert len({msk_date(item["air_at"]) for item in day["items"] if item["air_at"]}) <= 1, day["date_str"]

    window = {msk_date(item["air_at"]) for day in schedule_m for item in day["items"] if item["air_at"]}
    assert {msk_date(item["air_at"]) for day in schedule_v for item in day["items"] if item["air_at"]} <= window

    same = next(item for day in schedule_m for item in day["items"] if item["air_at"])
    shifted = next(item for day in schedule_v for item in day["items"] if item["link"] == same["link"] and item["episodes"] == same["episodes"])
    assert shifted["air_at"] == same["air_at"] - dt.timedelta(hours=7)


def test_schedule_in_user_timezone(fixture_html):
    _, _, schedule = parse(fixture_html("animego_home_moscow.html"))
    assert parser.localize_schedule(schedule, parser.MSK) is schedule  # по умолчанию — как есть, по Москве

    yekaterinburg = ZoneInfo("Asia/Yekaterinburg")
    local = parser.localize_schedule(schedule, yekaterinburg)
    first = schedule[0]["items"][0]
    moved = next(item for day in local for item in day["items"] if item["link"] == first["link"] and item["episodes"] == first["episodes"])
    assert moved["time"] == "16:57 (Екатеринбург)" and first["time"] == "14:57 (Москва)"  # оригинал из кэша не меняется

    for zone in (yekaterinburg, ZoneInfo("Asia/Vladivostok"), ZoneInfo("Europe/Kaliningrad")):
        for day in parser.localize_schedule(schedule, zone):
            dates = {parser._utc_naive_to(item["air_at"], zone).date().isoformat() for item in day["items"] if item["air_at"]}
            assert dates <= {day["date"]}, (zone, day["date_str"], dates)


def test_timezone_helpers():
    assert parser.zone_or_moscow(None).key == "Europe/Moscow"
    assert parser.zone_or_moscow("Не/Пояс").key == "Europe/Moscow"
    assert parser.zone_or_moscow("Asia/Omsk").key == "Asia/Omsk"
    assert parser.timezone_display_label(ZoneInfo("Asia/Yekaterinburg")) == "Екатеринбург"
    assert parser.timezone_display_label(ZoneInfo("Etc/GMT-5")) == "UTC+5"


def test_unknown_timezone_label_is_not_trusted(fixture_html):
    zone, updates, schedule = parse(fixture_html("animego_home_moscow.html").replace("(Москва)", "(Марс)"))
    assert zone is None
    assert all(update["released_at"] is None for update in updates)
    assert all(item["air_at"] is None for day in schedule for item in day["items"])
    assert any("(Марс)" in item["time"] for day in schedule for item in day["items"])
