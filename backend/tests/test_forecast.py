import datetime as dt
from types import SimpleNamespace

from services import forecast

URL = "https://animego.me/anime/x"
AIR_1 = dt.datetime(2026, 9, 7, 13, 0)
AIRINGS = {(URL, n): AIR_1 + (n - 1) * forecast.WEEK for n in range(1, 5)}
RELEASES = [
    SimpleNamespace(anime_url=URL, studio="AniLiberty", episode=1, released_at=AIRINGS[(URL, 1)] + dt.timedelta(hours=26)),
    SimpleNamespace(anime_url=URL, studio="AniLiberty", episode=2, released_at=AIRINGS[(URL, 2)] + dt.timedelta(hours=24)),
    SimpleNamespace(anime_url=URL, studio="AniLiberty", episode=3, released_at=AIRINGS[(URL, 3)] + dt.timedelta(hours=28)),
    SimpleNamespace(anime_url=URL, studio="AnimeVost", episode=3, released_at=AIRINGS[(URL, 3)] + dt.timedelta(hours=5)),
]
NOW = AIRINGS[(URL, 4)] - dt.timedelta(days=1)


def sub(voiceover, last_episode, total=None, url=URL):
    return SimpleNamespace(id=1, anime_url=url, voiceover=voiceover, last_episode=last_episode, total_episodes=total)


def at(value):
    return forecast._iso(value)


def test_title_history_forecast():
    result = forecast.forecast_subscription(sub("AniLiberty", "Серия 3"), RELEASES, AIRINGS, {}, NOW)
    air_4 = AIRINGS[(URL, 4)]
    assert result["basis"] == "title" and result["episode"] == 4
    assert result["expected_at"] == at(air_4 + dt.timedelta(hours=26))  # медиана задержек 24/26/28 ч
    assert result["earliest_at"] == at(air_4 + dt.timedelta(hours=24))
    assert result["latest_at"] == at(air_4 + dt.timedelta(hours=28))
    assert result["samples"] == 3 and result["overdue"] is False and result["air_estimated"] is False


def test_voiceover_match_is_case_insensitive():
    assert forecast.forecast_subscription(sub("anilIBERTY", "3 серия"), RELEASES, AIRINGS, {}, NOW)["basis"] == "title"
    assert forecast.voiceover_matches("Все", "что угодно")


def test_missing_airing_is_extrapolated_weekly():
    airings = {key: value for key, value in AIRINGS.items() if key[1] != 4}
    result = forecast.forecast_subscription(sub("AniLiberty", "Серия 3"), RELEASES, airings, {}, NOW)
    assert result["air_estimated"] is True and result["air_at"] == at(AIRINGS[(URL, 4)])


def test_no_forecast_when_released_or_finished():
    assert forecast.forecast_subscription(sub("AniLiberty", "Серия 2"), RELEASES, AIRINGS, {}, NOW) is None
    assert forecast.forecast_subscription(sub("AniLiberty", "Серия 12", total=12), RELEASES, AIRINGS, {}, NOW) is None


def test_any_voiceover_uses_original_airing():
    result = forecast.forecast_subscription(sub("Все", "Серия 3"), RELEASES, AIRINGS, {}, NOW)
    assert result["basis"] == "airing" and result["expected_at"] == at(AIRINGS[(URL, 4)])


def test_studio_wide_fallback():
    other = "https://animego.me/anime/y"
    airings = {(other, 5): dt.datetime(2026, 9, 12, 15, 0)}
    lags = {"aniliberty": [dt.timedelta(hours=h) for h in (10, 20, 30, 40, 50)]}
    result = forecast.forecast_subscription(sub("AniLiberty", "Серия 4", url=other), [], airings, lags, NOW)
    assert result["basis"] == "studio" and result["lag_hours"] == 30.0
    assert result["earliest_at"] == at(dt.datetime(2026, 9, 12, 15) + dt.timedelta(hours=20))
    few = {"aniliberty": [dt.timedelta(hours=10)]}
    assert forecast.forecast_subscription(sub("AniLiberty", "Серия 4", url=other), [], airings, few, NOW) is None


def test_cadence_fallback():
    url = "https://animego.me/anime/z"
    start = dt.datetime(2026, 8, 1, 18, 0)
    releases = [SimpleNamespace(anime_url=url, studio="Dream Cast", episode=n, released_at=start + (n - 1) * dt.timedelta(days=7)) for n in (1, 2, 3)]
    result = forecast.forecast_subscription(sub("Dream Cast", "Серия 3", url=url), releases, {}, {}, start)
    assert result["basis"] == "cadence" and result["expected_at"] == at(start + dt.timedelta(days=21))


def test_overdue_and_bad_samples():
    late = AIRINGS[(URL, 4)] + dt.timedelta(days=3)
    assert forecast.forecast_subscription(sub("AniLiberty", "Серия 3"), RELEASES, AIRINGS, {}, late)["overdue"] is True
    # Серия «вышла» раньше оригинала — это ошибка сопоставления, а не задержка
    bogus = [SimpleNamespace(anime_url=URL, studio="AniDUB", episode=3, released_at=AIRINGS[(URL, 3)] - dt.timedelta(days=3))]
    assert forecast.forecast_subscription(sub("AniDUB", "Серия 3"), bogus, AIRINGS, {}, NOW) is None


def test_forecast_for_later_episode():
    """Для недели: у отстающей озвучки прогнозируем и следующие серии"""
    result = forecast.forecast_subscription(sub("AniLiberty", "Серия 2"), RELEASES[:2], AIRINGS, {}, NOW, episode=4)
    assert result["episode"] == 4 and result["basis"] == "title"
