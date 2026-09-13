"""
YummyAnime как источник подписок.

- check_updates (каждые 15 минут): для тайтлов с подписками на YummyAnime берёт список серий, пишет серии
  в общую историю (episode_releases) и отправляет уведомления тем же кодом, что и для AnimeGO — с тихими часами
  и прогнозом. Данные тайтла (число серий, статус, дата следующей серии) обновляются раз в TITLE_REFRESH.
- status_info: число серий и статус для ежедневной проверки подписок — вместо страницы AnimeGO.
- title_details / subscribe / search / latest_updates — для бота и мини-аппа.

Названия озвучек сводятся к справочнику (voiceovers.canonical_names), одна студия в разных плеерах — одна озвучка.
Если YummyAnime недоступен, подписки AnimeGO это никак не затрагивает; после FAILURE_ALERT_CYCLES неудачных
проверок подряд админам приходит предупреждение.
"""
import asyncio
import datetime
import html
import logging
import time
from collections import defaultdict

import config
from database import requests as db
from services import stats, voiceovers, yummy
from services.notifier import notify_admins
from services.subscription_rules import subscription_block_reason

logger = logging.getLogger(__name__)

SOURCE = "yummy"
TITLE_REFRESH = datetime.timedelta(hours=6)
NOTIFY_LOOKBACK = datetime.timedelta(hours=48)
DETAILS_CACHE_TTL = 300
FEED_CACHE_TTL = 300
FAILURE_ALERT_CYCLES = 4

_check_lock = asyncio.Lock()
_details_cache: dict[int, tuple[float, dict]] = {}
_feed_cache: tuple[float, list[dict]] = (0.0, [])
_failed_cycles = 0
_alerted = False


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


async def merge_videos(videos: list[dict]) -> dict[str, dict[int, datetime.datetime]]:
    """Видео -> {озвучка из справочника: {серия: время первой загрузки}}; плееры одной студии сливаются"""
    raw = yummy.voiced_episodes(videos)
    names = await voiceovers.canonical_names(raw)
    # Сливаем по ключу: «Red Head Sound» и «RedHeadSound» — одна озвучка, даже если её ещё нет в справочнике
    display: dict[str, str] = {}
    for raw_name in sorted(raw):
        display.setdefault(voiceovers.key(names[raw_name]), names[raw_name])
    merged: dict[str, dict[int, datetime.datetime]] = defaultdict(dict)
    for raw_name, episodes in raw.items():
        target = merged[display[voiceovers.key(names[raw_name])]]
        for episode, uploaded in episodes.items():
            if episode not in target or uploaded < target[episode]:
                target[episode] = uploaded
    await voiceovers.remember(merged)
    return dict(merged)


def release_rows(url: str, title: str, merged: dict, now: datetime.datetime) -> list[dict]:
    return [
        {"anime_url": url, "anime_title": title, "studio": studio, "episode": episode, "released_at": min(uploaded, now)}
        for studio, episodes in merged.items()
        for episode, uploaded in episodes.items()
    ]


def dub_summary(merged: dict) -> list[dict]:
    """Озвучки тайтла для выбора: последняя серия и когда она появилась; свежие и далеко продвинувшиеся — первыми"""
    dubs = [
        {"name": name, "last_episode": max(episodes), "episodes": len(episodes), "updated_at": max(episodes.values())}
        for name, episodes in merged.items() if episodes
    ]
    return sorted(dubs, key=lambda dub: (-dub["last_episode"], -dub["updated_at"].timestamp(), dub["name"].lower()))


async def title_details(anime_id: int, use_cache: bool = True) -> dict:
    """Тайтл и его озвучки; YummyNotFound/YummyError — если получить не удалось"""
    cached = _details_cache.get(anime_id)
    if use_cache and cached and cached[0] > time.monotonic():
        return cached[1]

    anime = await yummy.get_anime(anime_id)
    videos = await yummy.get_videos(anime_id)
    row = yummy.title_row(anime)
    await db.upsert_yummy_titles([row])
    merged = await merge_videos(videos)
    details = {**row, "voiceovers": dub_summary(merged), "merged": merged}
    _details_cache[anime_id] = (time.monotonic() + DETAILS_CACHE_TTL, details)
    return details


async def search(query: str) -> list[dict]:
    """В базу не пишем: поиск не отдаёт число серий и затёр бы данные уже известного тайтла"""
    results = await yummy.search(query)
    return [yummy.title_row(item) for item in results if item.get("anime_id") and item.get("anime_url")]


async def subscribe(tg_id: int, anime_id: int, voiceover: str) -> tuple[bool, dict, dict]:
    """
    Подписка на тайтл YummyAnime с последней серии выбранной озвучки: (создана ли, тайтл, озвучка).
    ValueError — подписаться нельзя (текст для пользователя); YummyError — API недоступен
    """
    details = await title_details(anime_id)
    wanted = voiceovers.key(voiceover)
    dub = next((item for item in details["voiceovers"] if voiceovers.key(item["name"]) == wanted), None)
    if dub is None:
        raise ValueError("У этого тайтла на YummyAnime нет такой озвучки.")

    last_episode = f"Серия {dub['last_episode']}"
    reason = subscription_block_reason(yummy.rule_info(details), last_episode)
    if reason:
        raise ValueError(reason)

    # История нужна сразу: уведомления и прогноз строятся по ней
    await db.record_episode_releases(release_rows(details["url"], details["title"], details["merged"], _now()))
    created = await db.add_subscription(
        tg_id, details["title"], details["url"], last_episode, dub["name"],
        details["episodes_count"] or None, details["poster_url"], source=SOURCE, source_id=str(anime_id),
    )
    return created, details, dub


async def latest_updates() -> list[dict]:
    """Свежие серии с главной YummyAnime в формате ленты AnimeGO (+ source и source_id)"""
    global _feed_cache
    expires, cached = _feed_cache
    if expires > time.monotonic():
        return cached

    videos = await yummy.get_new_videos()
    names = await voiceovers.canonical_names({(video.get("dub_title") or "").strip() for video in videos} - {""})
    items, seen = [], set()
    for video in videos:
        episode = yummy.parse_episode(video.get("ep_title"))
        dub = (video.get("dub_title") or "").strip()
        if episode is None or not dub or not video.get("anime_url"):
            continue
        studio = names[dub]
        marker = (video.get("anime_id"), voiceovers.key(studio), episode)
        if marker in seen:
            continue
        seen.add(marker)
        items.append({
            "title": video.get("title") or video["anime_url"],
            "episode": f"Серия {episode}",
            "studio": studio,
            "link": yummy.site_url(video["anime_url"]),
            "poster_url": yummy.poster_url(video) or "",
            "released_at": yummy.timestamp(video.get("date")),
            "source": SOURCE,
            "source_id": str(video.get("anime_id")),
        })
    await voiceovers.remember([item["studio"] for item in items])
    _feed_cache = (time.monotonic() + FEED_CACHE_TTL, items)
    return items


async def _apply_title(subscriptions, row: dict, now: datetime.datetime) -> None:
    """Число серий в подписки и время следующей серии оригинала — в прогноз"""
    count = row.get("episodes_count") or None
    for sub in subscriptions:
        if count and sub.total_episodes != count:
            await db.update_total_episodes(sub.id, count)
            sub.total_episodes = count
    next_at, aired = row.get("next_episode_at"), row.get("episodes_aired")
    if next_at and next_at > now and aired is not None:
        await db.record_episode_airings(
            [{"anime_url": subscriptions[0].anime_url, "episode": aired + 1, "air_at": next_at}], source=SOURCE,
        )


async def status_info(source_id: str | None) -> dict | None:
    """Для ежедневной проверки подписок: {"total_episodes", "released"} или None, если YummyAnime не ответил"""
    if not source_id or not str(source_id).isdigit():
        return None
    try:
        row = yummy.title_row(await yummy.get_anime(int(source_id)))
    except yummy.YummyError as e:
        logger.warning(f"YummyAnime title {source_id} is unavailable: {e}")
        return None
    await db.upsert_yummy_titles([row])
    return {"total_episodes": row["episodes_count"] or None, "released": row["status"] == "released"}


async def _report_cycle(bot, failed: int, total: int) -> None:
    global _failed_cycles, _alerted
    if total and failed == total:
        _failed_cycles += 1
        if _failed_cycles >= FAILURE_ALERT_CYCLES and not _alerted:
            _alerted = True
            await notify_admins(
                bot,
                f"⚠️ YummyAnime не отвечает уже {_failed_cycles} проверок подряд — уведомления по подпискам "
                "на YummyAnime не приходят. Подписки AnimeGO работают как обычно.",
                level="WARNING",
            )
        return
    if _alerted:
        await notify_admins(bot, "✅ YummyAnime снова отвечает, уведомления по его подпискам возобновлены.", level="INFO")
    _failed_cycles, _alerted = 0, False


async def check_updates(bot) -> dict | None:
    """Фоновая задача: новые серии по подпискам на YummyAnime"""
    from services import checker  # checker импортирует этот модуль для проверки подписок

    if not config.YUMMY_ENABLED or _check_lock.locked():
        return None

    stats.set_source(stats.SOURCE_CHECKER)
    async with _check_lock:
        counts = {"titles": 0, "failed": 0}
        try:
            subscriptions = [
                sub for sub in await db.get_all_subscriptions()
                if sub.source == SOURCE and sub.source_id and str(sub.source_id).isdigit()
            ]
            groups = defaultdict(list)
            for sub in subscriptions:
                groups[int(sub.source_id)].append(sub)
            counts["titles"] = len(groups)
            if not groups:
                await _report_cycle(bot, 0, 0)
                return counts

            now = _now()
            titles = await db.get_yummy_titles(set(groups))
            for anime_id, group in groups.items():
                try:
                    videos = await yummy.get_videos(anime_id)
                    merged = await merge_videos(videos)
                    await db.record_episode_releases(release_rows(group[0].anime_url, group[0].anime_title, merged, now))
                    title = titles.get(anime_id)
                    if title is None or title.synced_at < now - TITLE_REFRESH:
                        row = yummy.title_row(await yummy.get_anime(anime_id))
                        await db.upsert_yummy_titles([row])
                        await _apply_title(group, row, now)
                    await stats.increment("yummy.request", "ok")
                except yummy.YummyNotFound:
                    logger.warning(f"YummyAnime title {anime_id} not found")
                except yummy.YummyError as e:
                    counts["failed"] += 1
                    await stats.increment("yummy.request", "failed")
                    logger.warning(f"YummyAnime check failed for {anime_id}: {e}")
            await _report_cycle(bot, counts["failed"], counts["titles"])

            releases_by_url = defaultdict(list)
            for release in await db.get_recent_releases(now - NOTIFY_LOOKBACK):
                releases_by_url[release.anime_url].append(release)
            for sub in subscriptions:
                if releases_by_url.get(sub.anime_url):
                    await checker.notify_subscription(bot, sub, releases_by_url[sub.anime_url])
            return counts
        except Exception as e:
            logger.error(f"YummyAnime checker error: {e}")
            await notify_admins(bot, f"Ошибка в проверке YummyAnime:\n<code>{html.escape(str(e))}</code>", level="ERROR")
            return None
