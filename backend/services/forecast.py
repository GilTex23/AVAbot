"""
Прогноз выхода следующей серии в озвучке.

История копится бесплатно из главной AnimeGO, которую чекер и так загружает каждые 20 минут:
- лента: когда серия вышла в конкретной озвучке («Серии 4 · AniMaunt — Сегодня, 10:20»);
- расписание: когда выходит оригинал серии («Серия 4 (из 12) — 16:00 (Москва)»).

Прогноз = выход оригинала + обычная задержка студии на этом тайтле
(если истории по тайтлу нет — типичная задержка студии по всем тайтлам,
если нет даты выхода оригинала — последняя серия в озвучке + обычный интервал между сериями).
"""
import datetime
import logging
from collections import defaultdict

from database import requests as db
from services.parser import max_episode_number, parse_episode_list

logger = logging.getLogger(__name__)

LAG_HISTORY_DAYS = 90
MAX_LAG = datetime.timedelta(days=21)
CLOCK_SKEW = datetime.timedelta(hours=2)
TITLE_SAMPLES = 6
MIN_STUDIO_SAMPLES = 3
MAX_AIRING_EXTRAPOLATION = 3
WEEK = datetime.timedelta(days=7)
OVERDUE_GRACE = datetime.timedelta(hours=12)
MIN_WINDOW = datetime.timedelta(hours=1)
ALL_VOICEOVERS = "Все"


def _studio_key(name: str | None) -> str:
    return (name or "").strip().lower()


def voiceover_matches(voiceover: str, studio: str) -> bool:
    """Подходит ли серия из ленты к озвучке подписки: «Все» — любая, иначе озвучка входит в название студии"""
    if voiceover == ALL_VOICEOVERS:
        return True
    voiceover_key, studio_key = _studio_key(voiceover), _studio_key(studio)
    return bool(voiceover_key) and (voiceover_key == studio_key or voiceover_key in studio_key)


def _lag(released_at: datetime.datetime, air_at: datetime.datetime | None) -> datetime.timedelta | None:
    if air_at is None:
        return None
    lag = released_at - air_at
    if lag < -CLOCK_SKEW or lag > MAX_LAG:
        return None  # это не та серия в расписании или криво распознанная дата
    return max(lag, datetime.timedelta(0))


def _percentile(values: list[datetime.timedelta], share: float) -> datetime.timedelta:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))]


def _iso(value: datetime.datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


async def record_home(home: dict, subscriptions) -> None:
    """Сохраняет историю из ленты и расписания; дозаполняет «?» числом серий из расписания"""
    now = datetime.datetime.utcnow()

    releases = {}
    for item in home.get("updates") or []:
        if not item.get("link") or not item.get("studio"):
            continue
        released_at = item.get("released_at") or now
        if released_at > now + CLOCK_SKEW:
            released_at = now
        # Выпуск может содержать несколько серий: "Серии 1, 7-8"
        for episode in parse_episode_list(item.get("episode")):
            releases[(item["link"], item["studio"], episode)] = {
                "anime_url": item["link"],
                "anime_title": item.get("title") or "Unknown",
                "studio": item["studio"],
                "episode": episode,
                "released_at": released_at,
            }

    airings = {}
    totals = {}
    for day in home.get("schedule") or []:
        for item in day.get("items") or []:
            # Без времени (часто у китайских тайтлов) выход не записываем — прогноз пойдёт по интервалу между сериями
            if item.get("air_at"):
                for episode in item.get("episodes") or []:
                    airings[(item["link"], episode)] = {
                        "anime_url": item["link"],
                        "episode": episode,
                        "air_at": item["air_at"],
                    }
            if item.get("total_episodes"):
                totals[item["link"]] = item["total_episodes"]

    await db.record_episode_releases(list(releases.values()))
    await db.record_episode_airings(list(airings.values()))

    missing_totals = {sub.anime_url for sub in subscriptions if sub.total_episodes is None}
    for url in missing_totals & totals.keys():
        await db.fill_total_episodes(url, totals[url])
        logger.info(f"Total episodes for {url} taken from schedule: {totals[url]}")


def _air_time(url: str, episode: int, airings: dict) -> tuple[datetime.datetime | None, bool]:
    """Выход серии в Японии: из расписания или по соседней серии (+7 дней за серию). Второе значение — оценка ли это"""
    if (url, episode) in airings:
        return airings[(url, episode)], False

    known = [(known_episode, air_at) for (known_url, known_episode), air_at in airings.items() if known_url == url]
    if not known:
        return None, False
    nearest_episode, nearest_air = min(known, key=lambda pair: abs(pair[0] - episode))
    if abs(nearest_episode - episode) > MAX_AIRING_EXTRAPOLATION:
        return None, False
    return nearest_air + (episode - nearest_episode) * WEEK, True


def _cadence(releases: list) -> datetime.timedelta | None:
    """Обычный интервал между сериями в этой озвучке"""
    ordered = sorted(releases, key=lambda release: release.episode)
    intervals = [
        (current.released_at - previous.released_at) / (current.episode - previous.episode)
        for previous, current in zip(ordered, ordered[1:])
        if current.episode > previous.episode and current.released_at > previous.released_at
    ]
    if not intervals:
        return None
    return min(max(_percentile(intervals[-TITLE_SAMPLES:], 0.5), datetime.timedelta(days=1)), datetime.timedelta(days=14))


def _result(episode, expected, earliest, latest, air_at, air_estimated, basis, lags, now) -> dict:
    if latest - earliest < MIN_WINDOW:
        earliest, latest = expected - MIN_WINDOW / 2, expected + MIN_WINDOW / 2
    return {
        "episode": episode,
        "expected_at": _iso(expected),
        "earliest_at": _iso(earliest),
        "latest_at": _iso(latest),
        "air_at": _iso(air_at),
        "air_estimated": air_estimated,
        "basis": basis,
        "lag_hours": round(_percentile(lags, 0.5).total_seconds() / 3600, 1) if lags else None,
        "samples": len(lags),
        "overdue": now > latest + OVERDUE_GRACE,
    }


def forecast_subscription(
    sub, url_releases: list, airings: dict, studio_lags: dict, now: datetime.datetime, episode: int | None = None,
) -> dict | None:
    """Прогноз для серии episode (по умолчанию — следующей после последней вышедшей в подписке)"""
    target = episode or int(max_episode_number(sub.last_episode)) + 1
    if sub.total_episodes and target > sub.total_episodes:
        return None

    is_all = sub.voiceover == ALL_VOICEOVERS
    own = [release for release in url_releases if voiceover_matches(sub.voiceover, release.studio)]
    if any(release.episode >= target for release in own):
        return None  # серия уже вышла — уведомление придёт при следующей проверке

    air_at, air_estimated = _air_time(sub.anime_url, target, airings)
    if is_all:
        # Для «Все» ориентир — выход в Японии: первая озвучка обычно появляется вскоре после него
        if air_at is None:
            return None
        return _result(target, air_at, air_at, air_at, air_at, air_estimated, "airing", [], now)

    if air_at is not None:
        title_lags = [
            lag for release in sorted(own, key=lambda release: release.released_at, reverse=True)
            if (lag := _lag(release.released_at, airings.get((sub.anime_url, release.episode)))) is not None
        ][:TITLE_SAMPLES]
        if title_lags:
            return _result(
                target, air_at + _percentile(title_lags, 0.5), air_at + min(title_lags), air_at + max(title_lags),
                air_at, air_estimated, "title", title_lags, now,
            )

        studio_samples = [lag for studio, lags in studio_lags.items() if voiceover_matches(sub.voiceover, studio) for lag in lags]
        if len(studio_samples) >= MIN_STUDIO_SAMPLES:
            # По чужим тайтлам разброс больше, поэтому берём середину распределения, а не крайние значения
            return _result(
                target, air_at + _percentile(studio_samples, 0.5),
                air_at + _percentile(studio_samples, 0.25), air_at + _percentile(studio_samples, 0.75),
                air_at, air_estimated, "studio", studio_samples, now,
            )

    cadence = _cadence(own)
    if cadence is not None:
        last_release = max(own, key=lambda release: release.episode)
        expected = last_release.released_at + (target - last_release.episode) * cadence
        return _result(
            target, expected, expected - datetime.timedelta(days=1), expected + datetime.timedelta(days=1),
            air_at, air_estimated, "cadence", [], now,
        )
    return None


async def _load_history(subscriptions, now: datetime.datetime):
    urls = {sub.anime_url for sub in subscriptions}

    releases_by_url = defaultdict(list)
    for release in await db.get_episode_releases(urls):
        releases_by_url[release.anime_url].append(release)
    airings = {(airing.anime_url, airing.episode): airing.air_at for airing in await db.get_episode_airings(urls)}

    studio_lags = defaultdict(list)
    for studio, released_at, air_at in await db.get_release_lag_samples(now - datetime.timedelta(days=LAG_HISTORY_DAYS)):
        lag = _lag(released_at, air_at)
        if lag is not None:
            studio_lags[_studio_key(studio)].append(lag)
    return releases_by_url, airings, studio_lags


async def build_forecasts(subscriptions) -> dict[int, dict | None]:
    if not subscriptions:
        return {}

    now = datetime.datetime.utcnow()
    releases_by_url, airings, studio_lags = await _load_history(subscriptions, now)
    return {
        sub.id: forecast_subscription(sub, releases_by_url[sub.anime_url], airings, studio_lags, now)
        for sub in subscriptions
    }


WEEK_EPISODES_PER_SUBSCRIPTION = 3


async def build_week(subscriptions, days: int = 7) -> list[dict]:
    """
    Серии по подпискам, которые ожидаются в ближайшие days дней (и задерживающиеся), по времени.
    У отстающей озвучки за неделю может выйти несколько серий — прогнозируем до трёх подряд.
    """
    if not subscriptions:
        return []

    now = datetime.datetime.utcnow()
    horizon = now + datetime.timedelta(days=days)
    releases_by_url, airings, studio_lags = await _load_history(subscriptions, now)

    items = []
    for sub in subscriptions:
        first = int(max_episode_number(sub.last_episode)) + 1
        for episode in range(first, first + WEEK_EPISODES_PER_SUBSCRIPTION):
            prediction = forecast_subscription(sub, releases_by_url[sub.anime_url], airings, studio_lags, now, episode)
            if prediction is None or datetime.datetime.fromisoformat(prediction["expected_at"].rstrip("Z")) > horizon:
                break
            items.append({"subscription_id": sub.id, "forecast": prediction})
            if prediction["overdue"]:
                break  # следующие серии этой озвучки тоже поедут, пока не выйдет текущая

    return sorted(items, key=lambda item: item["forecast"]["expected_at"])
