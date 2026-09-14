"""
Клиент API YummyAnime (api.yani.tv) и разбор его ответов.

Запросы идут по одному с небольшой паузой; на сбои сети и 5xx — один повтор, дальше YummyError.
Токен приложения (YUMMY_APP_TOKEN) передаётся в X-Application, если задан.
"""
import asyncio
import datetime
import logging
import re
import time

import aiohttp

import config

logger = logging.getLogger(__name__)

REQUEST_INTERVAL = 0.3
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 2
SEARCH_LIMIT = 10
DEEP_LINK_PREFIX = "y"
_PAYLOAD_RE = re.compile(rf"^{DEEP_LINK_PREFIX}(\d{{1,9}})$")
_EPISODE_RE = re.compile(r"^\s*(\d{1,5})\s*$")


class YummyError(Exception):
    pass


class YummyNotFound(YummyError):
    pass


_lock = asyncio.Lock()
_last_request_at = 0.0


def _headers() -> dict:
    headers = {"Accept": "application/json, image/avif, image/webp", "Lang": "ru", "User-Agent": "AnimeVoiceNotifier"}
    if config.YUMMY_APP_TOKEN:
        headers["X-Application"] = config.YUMMY_APP_TOKEN
    return headers


async def _get(path: str, params: dict | None = None):
    global _last_request_at
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        async with _lock:
            wait = _last_request_at + REQUEST_INTERVAL - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with aiohttp.ClientSession(headers=_headers()) as session:
                    async with session.get(
                        f"{config.YUMMY_API_URL}{path}", params=params, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    ) as response:
                        status = response.status
                        body = await response.json(content_type=None) if status < 500 else await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                status, body = None, None
                last_error = f"{type(e).__name__}: {e}"
            finally:
                _last_request_at = time.monotonic()

        if status == 200 and isinstance(body, dict) and "response" in body:
            return body["response"]
        if status == 404:
            raise YummyNotFound("Not found")
        if status is not None and status < 500:
            message = body.get("error") if isinstance(body, dict) else None
            raise YummyError(f"HTTP {status}: {message or 'unexpected response'}")
        if status is not None:
            last_error = f"HTTP {status}"
        if attempt < MAX_ATTEMPTS:
            await asyncio.sleep(1.5)
    raise YummyError(last_error or "request failed")


async def search(query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    return await _get("/search", {"q": query, "limit": limit})


async def get_anime(anime_id: int) -> dict:
    return await _get(f"/anime/{int(anime_id)}")


async def get_videos(anime_id: int) -> list[dict]:
    return await _get(f"/anime/{int(anime_id)}/videos")


async def get_new_videos() -> list[dict]:
    """Свежие серии с главной (~20 последних загрузок)"""
    feed = await _get("/feed")
    return (feed or {}).get("new_videos") or []


# --- Разбор ответов ---

def site_url(alias: str) -> str:
    return f"{config.YUMMY_SITE_URL}/catalog/item/{alias}"


def poster_url(item: dict) -> str | None:
    poster = item.get("poster") or {}
    url = poster.get("big") or poster.get("medium") or poster.get("fullsize")
    if not url or "default-poster" in url:
        return None
    return f"https:{url}" if url.startswith("//") else url


def parse_episode(number) -> int | None:
    """Номер серии «8» -> 8; «8.5», «1-2», «Фильм» — не серии для подписок"""
    match = _EPISODE_RE.match(str(number or ""))
    return int(match.group(1)) if match else None


def timestamp(value) -> datetime.datetime | None:
    """Unix-время API -> naive UTC"""
    try:
        return datetime.datetime.fromtimestamp(int(value), datetime.timezone.utc).replace(tzinfo=None) if value else None
    except (TypeError, ValueError, OverflowError):
        return None


def title_row(anime: dict) -> dict:
    """Ответ /anime/{id} или /search -> строка yummy_titles"""
    episodes = anime.get("episodes") or {}
    rating = anime.get("rating") or {}
    return {
        "id": int(anime["anime_id"]),
        "alias": anime["anime_url"],
        "url": site_url(anime["anime_url"]),
        "title": anime.get("title") or anime["anime_url"],
        "poster_url": poster_url(anime),
        "shikimori_id": ((anime.get("remote_ids") or {}).get("shikimori_id")) or None,
        "kind": (anime.get("type") or {}).get("name"),
        "status": (anime.get("anime_status") or {}).get("alias"),
        "year": anime.get("year"),
        "episodes_count": episodes.get("count"),
        "episodes_aired": episodes.get("aired"),
        "next_episode_at": timestamp(episodes.get("next_date")),
        # Только своя оценка: копии оценок других сайтов у YummyAnime устаревают
        "rating": round(float(rating["average"]), 2) if rating.get("average") else None,
        "rating_votes": rating.get("counters") or None,
    }


def rule_info(row: dict) -> dict:
    """Строка yummy_titles -> данные для subscription_block_reason (как со страницы AnimeGO)"""
    return {
        "type": "Фильм" if "фильм" in (row.get("kind") or "").lower() else row.get("kind"),
        "status": "Вышел" if row.get("status") == "released" else row.get("status"),
        "total_episodes": row.get("episodes_count") or None,
    }


def voiced_episodes(videos: list[dict]) -> dict[str, dict[int, datetime.datetime]]:
    """Видео по плеерам -> {сырое название озвучки: {серия: самое раннее время загрузки}}"""
    result: dict[str, dict[int, datetime.datetime]] = {}
    for video in videos or []:
        dubbing = ((video.get("data") or {}).get("dubbing") or "").strip()
        episode = parse_episode(video.get("number"))
        uploaded = timestamp(video.get("date"))
        if not dubbing or episode is None or uploaded is None:
            continue
        episodes = result.setdefault(dubbing, {})
        if episode not in episodes or uploaded < episodes[episode]:
            episodes[episode] = uploaded
    return result


def parse_payload(payload: str | None) -> int | None:
    match = _PAYLOAD_RE.match((payload or "").strip())
    return int(match.group(1)) if match else None
