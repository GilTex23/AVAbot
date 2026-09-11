import datetime as dt

import pytest
from bs4 import BeautifulSoup

from conftest import ADMIN_ID
from services import health, parser
from services.subscription_rules import subscription_block_reason

FETCHED_AT = dt.datetime(2026, 9, 11, 13, 49, tzinfo=parser.MSK)


@pytest.mark.parametrize("info, last_episode, allowed", [
    ({"type": "Сериал", "status": "Онгоинг", "total_episodes": None}, "Серия 3", True),
    ({"type": "Фильм", "status": "Вышел", "total_episodes": 1}, "Серия 0", False),
    # Оригинал вышел, а озвучка отстаёт — подписка нужна
    ({"type": "Сериал", "status": "Вышел", "total_episodes": 14}, "Серии 12", True),
    ({"type": "Сериал", "status": "Вышел", "total_episodes": 14}, "Серия 14", False),
    ({"type": "Сериал", "status": "Вышел", "total_episodes": 14}, "Серии 1, 13-14", False),
    (None, "Серия 1", True),
])
def test_subscription_block_reason(info, last_episode, allowed):
    assert (subscription_block_reason(info, last_episode) is None) is allowed


def home_from(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    label, zone = parser._page_timezone(soup)
    return {
        "updates": parser._parse_updates(soup, FETCHED_AT, zone),
        "schedule": parser._parse_schedule(soup, FETCHED_AT, zone),
        "timezone": label,
        "timezone_known": zone is not None,
    }


def test_find_problems(fixture_html):
    html = fixture_html("animego_home_moscow.html")
    assert health.find_problems(home_from(html)) == []
    assert health.find_problems(None) == ["Не удалось загрузить главную AnimeGO"]
    assert any("Незнакомый часовой пояс" in problem for problem in health.find_problems(home_from(html.replace("(Москва)", "(Марс)"))))

    broken = home_from(html)
    broken["updates"] = []
    assert any("Лента обновлений" in problem for problem in health.find_problems(broken))


async def test_alert_after_threshold_and_recovery(fixture_html, fake_bot, monkeypatch):
    monkeypatch.setattr(health, "home_health", health.HomeHealth())
    good = home_from(fixture_html("animego_home_moscow.html"))

    for _ in range(health.FAILURE_THRESHOLD - 1):
        await health.record_home_result(fake_bot, None)
    assert fake_bot.texts_for(ADMIN_ID) == []

    await health.record_home_result(fake_bot, None)
    await health.record_home_result(fake_bot, None)
    alerts = fake_bot.texts_for(ADMIN_ID)
    assert len(alerts) == 1 and "Проблема с главной AnimeGO" in alerts[0]

    await health.record_home_result(fake_bot, good)
    assert "снова работает" in fake_bot.texts_for(ADMIN_ID)[-1]
    snapshot = health.snapshot()
    assert snapshot["problems"] == [] and snapshot["updates_count"] == 20 and snapshot["timezone"] == "Москва"
