"""
Shikimori для тайтлов с подписками: сопоставление, обновление данных и что из них можно брать.

Что делает фоновая задача (sync):
- ищет на Shikimori тайтлы, которые ещё не сопоставлены (не найденные и неоднозначные — повторно раз в неделю
  или сразу, если на странице AnimeGO поменялись данные для поиска; ошибки сети — через час);
- обновляет данные сопоставленных тайтлов (онгоинги — каждые REFRESH_ONGOING, остальные — раз в неделю);
- записывает время выхода следующей серии оригинала, если его нет в расписании AnimeGO.

Если тайтла на Shikimori нет или он не сопоставлен, всё работает по AnimeGO, как раньше.
Данным Shikimori не доверяем, если нумерация серий расходится с AnimeGO (сквозная нумерация сезонов и т.п.).
"""
import asyncio
import datetime
import logging

import config
from database import requests as db
from services import anime_titles, shikimori, shikimori_match, stats
from services.parser import max_episode_number

logger = logging.getLogger(__name__)

MATCHED_STATUSES = ("matched", "manual")
RETRY_STATUSES = ("not_found", "ambiguous")
MATCH_RETRY = datetime.timedelta(days=7)
ERROR_RETRY = datetime.timedelta(hours=1)
REFRESH_ONGOING = datetime.timedelta(hours=6)
REFRESH_OTHER = datetime.timedelta(days=7)
# Для решений о подписках (число серий, завершение) данные должны быть свежими
FRESH_FOR_STATUS = datetime.timedelta(days=2)

_sync_lock = asyncio.Lock()
_background_tasks: set[asyncio.Task] = set()


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def match_due(title, now: datetime.datetime) -> bool:
    status, checked = title.shikimori_status, title.shikimori_checked_at
    if status == "pending" or (checked is None and status in (*RETRY_STATUSES, "error")):
        return True
    if status in RETRY_STATUSES:
        return checked < now - MATCH_RETRY or (title.meta_updated_at is not None and title.meta_updated_at > checked)
    if status == "error":
        return checked < now - ERROR_RETRY
    return False  # matched, manual, absent


def refresh_due(anime, now: datetime.datetime) -> bool:
    if anime is None:
        return True
    period = REFRESH_ONGOING if anime.status in ("ongoing", "anons") else REFRESH_OTHER
    return anime.synced_at < now - period


def meta_of(title) -> shikimori_match.TitleMeta:
    return shikimori_match.TitleMeta(
        russian=title.title,
        alt_names=list(title.alt_names or []),
        english=title.english_title,
        kind=title.kind,
        aired_on=title.aired_on,
        episodes=title.episodes,
    )


async def match_title(title) -> str:
    """Ищет тайтл на Shikimori и сохраняет результат; возвращает статус"""
    meta = meta_of(title)
    candidates = []
    try:
        for query in meta.search_queries():
            candidates += await shikimori.search(query)
    except shikimori.ShikimoriError as e:
        logger.warning(f"Shikimori search failed for «{title.title}»: {e}")
        await db.set_title_shikimori(title.id, "error", error=str(e)[:500])
        await stats.increment("shikimori.match", "error")
        return "error"

    result = shikimori_match.choose(meta, candidates)
    if result.status == "matched":
        found = next(candidate for candidate in candidates if int(candidate["id"]) == result.shikimori_id)
        await db.upsert_shikimori_animes([shikimori.to_row(found)])
        await db.set_title_shikimori(title.id, "matched", result.shikimori_id, result.candidates)
        logger.info(f"Shikimori match: «{title.title}» -> {result.shikimori_id}")
    else:
        await db.set_title_shikimori(title.id, result.status, candidates=result.candidates or None)
        logger.info(f"Shikimori {result.status}: «{title.title}» ({len(result.candidates)} candidates)")
    await stats.increment("shikimori.match", result.status)
    return result.status


async def set_manual(anime_id: int, shikimori_id: int) -> None:
    """Админ выбрал тайтл на Shikimori; ShikimoriError/LookupError — если такого тайтла там нет"""
    found = await shikimori.get_by_ids([shikimori_id])
    if not found:
        raise LookupError(f"На Shikimori нет тайтла с id {shikimori_id}")
    await db.upsert_shikimori_animes([shikimori.to_row(found[0])])
    title = await db.get_anime_title(anime_id)
    await db.set_title_shikimori(anime_id, "manual", shikimori_id, title.shikimori_candidates if title else None)
    await record_airings([await db.get_anime_title(anime_id)])


def airing_row(title, anime, max_released: int | None, now: datetime.datetime) -> dict | None:
    """
    Выход следующей серии оригинала по Shikimori. Нет, если серия уже вышла, время неизвестно
    или нумерация не сходится: в ленте AnimeGO серия с номером больше, чем вышло в оригинале
    """
    if anime is None or anime.next_episode_at is None or anime.next_episode_at <= now or anime.episodes_aired is None:
        return None
    if max_released is not None and max_released > anime.episodes_aired:
        return None
    return {"anime_url": title.url, "episode": anime.episodes_aired + 1, "air_at": anime.next_episode_at}


async def record_airings(titles) -> int:
    now = _now()
    matched = [title for title in titles if title and title.shikimori_status in MATCHED_STATUSES and title.shikimori]
    max_released = await db.get_max_released_episodes({title.url for title in matched})
    rows = [row for title in matched if (row := airing_row(title, title.shikimori, max_released.get(title.url), now))]
    await db.record_episode_airings(rows, source="shikimori")
    return len(rows)


async def sync(force: bool = False) -> dict | None:
    """Фоновая задача: сопоставление, обновление данных и время выхода серий"""
    if not config.SHIKIMORI_ENABLED:
        return None
    if _sync_lock.locked():
        logger.info("Shikimori sync is already running")
        return None

    async with _sync_lock:
        counts = {"titles": 0, "matched": 0, "not_found": 0, "ambiguous": 0, "error": 0, "refreshed": 0, "airings": 0}
        now = _now()
        titles = [title for title, _ in await db.get_subscribed_titles()]
        counts["titles"] = len(titles)

        for title in titles:
            if (force and title.shikimori_status in (*RETRY_STATUSES, "error", "pending")) or match_due(title, now):
                counts[await match_title(title)] += 1

        titles = [title for title, _ in await db.get_subscribed_titles()]
        stale_ids = [
            title.shikimori_id for title in titles
            if title.shikimori_status in MATCHED_STATUSES and title.shikimori_id and (force or refresh_due(title.shikimori, now))
        ]
        # Тайтлы подписок на YummyAnime связаны с Shikimori напрямую — их оценка и данные тоже нужны
        yummy_ids = await db.get_subscribed_yummy_shikimori_ids()
        known = await db.get_shikimori_animes(yummy_ids)
        stale_ids += [id_ for id_ in yummy_ids if id_ not in stale_ids and (force or refresh_due(known.get(id_), now))]
        if stale_ids:
            try:
                rows = [shikimori.to_row(anime) for anime in await shikimori.get_by_ids(stale_ids)]
                await db.upsert_shikimori_animes(rows)
                counts["refreshed"] = len(rows)
                titles = [title for title, _ in await db.get_subscribed_titles()]
            except shikimori.ShikimoriError as e:
                logger.warning(f"Shikimori refresh failed: {e}")
                counts["error"] += 1

        counts["airings"] = await record_airings(titles)
        logger.info(f"Shikimori sync finished: {counts}")
        return counts


def is_sync_running() -> bool:
    return _sync_lock.locked()


def kick(url: str) -> None:
    """После новой подписки: сопоставить тайтл сразу, не дожидаясь фоновой задачи"""
    anime_id = anime_titles.anime_id(url)
    if not config.SHIKIMORI_ENABLED or anime_id is None:
        return

    async def run():
        try:
            title = await db.get_anime_title(anime_id)
            if title is None:
                return
            if match_due(title, _now()):
                await match_title(title)
                title = await db.get_anime_title(anime_id)
            await record_airings([title])
        except Exception as e:
            logger.error(f"Shikimori match after subscription failed for {url}: {e}")

    task = asyncio.create_task(run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def status_from_shikimori(title, subscriptions, now: datetime.datetime | None = None) -> dict | None:
    """
    Замена страницы тайтла AnimeGO в проверке подписок: {"total_episodes", "released"} или None — тогда нужна страница.
    Число серий берём у вышедшего тайтла или если оно совпадает с числом серий на AnimeGO; и только если ни одна
    подписка не ушла дальше этого числа (иначе нумерация у сайтов разная и подписку сняли бы раньше времени)
    """
    now = now or _now()
    if title is None or title.shikimori_status not in MATCHED_STATUSES or title.shikimori is None:
        return None
    anime = title.shikimori
    if anime.synced_at < now - FRESH_FOR_STATUS or anime.status not in ("anons", "ongoing", "released"):
        return None

    episodes = anime.episodes or None
    last_seen = max((max_episode_number(sub.last_episode) for sub in subscriptions), default=0)
    if episodes is not None and last_seen > episodes:
        return None
    # AnimeGO уже знает другое число серий — верим AnimeGO и смотрим страницу
    if episodes is not None and any(sub.total_episodes is not None and sub.total_episodes != episodes for sub in subscriptions):
        return None
    released = anime.status == "released"
    if released and episodes is None:
        return None
    trusted_total = episodes if released or (episodes is not None and title.episodes == episodes) else None
    return {"total_episodes": trusted_total, "released": released}
