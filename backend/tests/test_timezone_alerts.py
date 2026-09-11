import datetime as dt
from collections import deque
from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup

from conftest import ADMIN_ID
from services import health, parser, timezone_alerts

FETCHED_AT = dt.datetime(2026, 9, 11, 13, 49, tzinfo=parser.MSK)


@pytest.fixture(autouse=True)
def fresh_reports(monkeypatch):
    monkeypatch.setattr(timezone_alerts, "_reported_pages", deque(maxlen=50))


def known_airings(html: str) -> list:
    """Время выхода серий, уже записанное в историю с «нормальной» страницы"""
    soup = BeautifulSoup(html, "html.parser")
    schedule = parser._parse_schedule(soup, FETCHED_AT, parser._page_zone(soup))
    return [
        SimpleNamespace(anime_url=item["link"], episode=episode, air_at=item["air_at"])
        for day in schedule for item in day["items"] if item["air_at"] for episode in item["episodes"]
    ]


def serve(monkeypatch, html: str, airings: list):
    async def fake_get_html(url, session=None, bot=None):
        return html

    async def fake_airings(urls):
        return [airing for airing in airings if airing.anime_url in urls]

    monkeypatch.setattr(parser, "get_html", fake_get_html)
    monkeypatch.setattr(timezone_alerts.db, "get_episode_airings", fake_airings)


async def test_unknown_label_reported_with_offset_and_suggestion(fixture_html, fake_bot, monkeypatch):
    moscow = fixture_html("animego_home_moscow.html")
    serve(monkeypatch, moscow.replace("(Москва)", "(Марс)"), known_airings(moscow))

    await parser.get_updates(fake_bot)
    await parser.get_schedule(fake_bot)  # та же страница из кэша — не новый случай

    messages = fake_bot.texts_for(ADMIN_ID)
    assert len(messages) == 1
    message = messages[0]
    assert "Незнакомый часовой пояс" in message and "«Марс»" in message
    assert "(Марс)" in message and "Сегодня, 12:50" in message  # примеры со страницы
    assert "UTC+3" in message and "<code>'Марс': 'Europe/Moscow',</code>" in message


async def test_each_new_page_is_reported(fixture_html, fake_bot, monkeypatch):
    moscow = fixture_html("animego_home_moscow.html")
    armenia = fixture_html("animego_home_armenia.html")
    serve(monkeypatch, moscow.replace("(Москва)", "(Марс)"), known_airings(moscow))
    await parser.get_updates(fake_bot)
    serve(monkeypatch, armenia.replace("(Армения)", "(Юпитер)"), known_airings(moscow))
    await parser.get_updates(fake_bot)

    messages = fake_bot.texts_for(ADMIN_ID)
    assert len(messages) == 2
    assert "UTC+4" in messages[1] and "'Юпитер': 'Europe/Samara'" in messages[1]


async def test_ambiguous_label_and_missing_history(fixture_html, fake_bot, monkeypatch):
    moscow = fixture_html("animego_home_moscow.html")
    serve(monkeypatch, moscow.replace("(Москва)", "(Восточная Европа)"), [])
    await parser.get_updates(fake_bot)

    message = fake_bot.texts_for(ADMIN_ID)[0]
    assert "Неоднозначный часовой пояс" in message
    assert "Смещение определить не удалось" in message and "'Регион/Город'" in message


async def test_known_label_is_not_reported(fixture_html, fake_bot, monkeypatch):
    serve(monkeypatch, fixture_html("animego_home_moscow.html"), [])
    await parser.get_updates(fake_bot)
    assert fake_bot.texts_for(ADMIN_ID) == []


async def test_unknown_timezone_is_not_a_parser_failure(fixture_html, fake_bot, monkeypatch):
    """О поясе пишет timezone_alerts; общий сигнал «уведомления могут не приходить» из-за него не срабатывает"""
    monkeypatch.setattr(health, "home_health", health.HomeHealth())
    moscow = fixture_html("animego_home_moscow.html")
    serve(monkeypatch, moscow.replace("(Москва)", "(Марс)"), [])
    home = await parser.get_home(fake_bot)

    for _ in range(health.FAILURE_THRESHOLD + 1):
        await health.record_home_result(fake_bot, home)

    assert health.home_health.consecutive_failures == 0
    assert any("Незнакомый часовой пояс" in problem for problem in health.home_health.problems)
    assert not any("Проблема с главной" in text for text in fake_bot.texts_for(ADMIN_ID))
