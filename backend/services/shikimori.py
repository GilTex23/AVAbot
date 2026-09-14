"""
Клиент GraphQL API Shikimori.

Лимиты Shikimori — 5 запросов в секунду и 90 в минуту, поэтому запросы идут по одному с паузой REQUEST_INTERVAL.
На 429 и сбои сети — несколько повторов с паузой; дальше ShikimoriError, и вызывающий код работает без Shikimori.
"""
import asyncio
import datetime
import logging
import re
import time

import aiohttp

import config

logger = logging.getLogger(__name__)

REQUEST_INTERVAL = 0.7  # ~85 запросов в минуту
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 3
IDS_PER_REQUEST = 50
SEARCH_LIMIT = 10

ANIME_FIELDS = """
    id name russian english japanese synonyms kind status episodes episodesAired
    airedOn { date } releasedOn { date } nextEpisodeAt score url
"""
SEARCH_QUERY = f"query($search: String, $limit: PositiveInt) {{ animes(search: $search, limit: $limit) {{ {ANIME_FIELDS} }} }}"
IDS_QUERY = f"query($ids: String, $limit: PositiveInt) {{ animes(ids: $ids, limit: $limit) {{ {ANIME_FIELDS} }} }}"


class ShikimoriError(Exception):
    pass


_lock = asyncio.Lock()
_last_request_at = 0.0


async def _post(payload: dict) -> list[dict]:
    global _last_request_at
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        async with _lock:
            wait = _last_request_at + REQUEST_INTERVAL - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with aiohttp.ClientSession(headers={"User-Agent": config.SHIKIMORI_USER_AGENT}) as session:
                    async with session.post(
                        f"{config.SHIKIMORI_URL}/api/graphql", json=payload, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                    ) as response:
                        status = response.status
                        retry_after = response.headers.get("Retry-After")
                        body = await response.json(content_type=None) if status == 200 else await response.text()
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
                status, retry_after, body = None, None, None
                last_error = f"{type(e).__name__}: {e}"
            finally:
                _last_request_at = time.monotonic()

        if status == 200:
            if isinstance(body, dict) and body.get("errors"):
                raise ShikimoriError(f"GraphQL error: {body['errors'][0].get('message', body['errors'])}")
            animes = ((body or {}).get("data") or {}).get("animes") if isinstance(body, dict) else None
            if animes is None:
                raise ShikimoriError("Unexpected response: no data.animes")
            return animes

        if status is not None:
            last_error = f"HTTP {status}"
        if status is not None and status < 500 and status != 429:
            raise ShikimoriError(last_error)
        if attempt < MAX_ATTEMPTS:
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2.0 * attempt
            logger.warning(f"Shikimori request failed ({last_error}), retry in {delay:.0f}s")
            await asyncio.sleep(delay)
    raise ShikimoriError(last_error or "request failed")


async def search(query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    return await _post({"query": SEARCH_QUERY, "variables": {"search": query, "limit": limit}})


async def get_by_ids(ids: list[int]) -> list[dict]:
    result = []
    unique = sorted(set(ids))
    for start in range(0, len(unique), IDS_PER_REQUEST):
        chunk = unique[start:start + IDS_PER_REQUEST]
        result += await _post({"query": IDS_QUERY, "variables": {"ids": ",".join(map(str, chunk)), "limit": len(chunk)}})
    return result


def _date(value) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _utc_naive(value) -> datetime.datetime | None:
    try:
        parsed = datetime.datetime.fromisoformat(value) if value else None
    except ValueError:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def to_row(anime: dict) -> dict:
    """Ответ GraphQL -> строка shikimori_animes"""
    return {
        "id": int(anime["id"]),
        "name": anime.get("name") or anime.get("russian") or str(anime["id"]),
        "russian": anime.get("russian"),
        "kind": anime.get("kind"),
        "status": anime.get("status"),
        "episodes": anime.get("episodes"),
        "episodes_aired": anime.get("episodesAired"),
        "next_episode_at": _utc_naive(anime.get("nextEpisodeAt")),
        "aired_on": _date((anime.get("airedOn") or {}).get("date")),
        "released_on": _date((anime.get("releasedOn") or {}).get("date")),
        # У анонсов Shikimori отдаёт 0 — это не оценка
        "score": anime.get("score") or None,
        "url": anime.get("url"),
    }


def parse_id(value) -> int | None:
    """Id из числа, «52991» или ссылки https://shikimori.io/animes/z52991-sousou-no-frieren"""
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value or "").strip()
    if text.isdigit():
        return int(text) or None
    match = re.search(r"/animes/[a-z]*(\d+)", text)
    return int(match.group(1)) if match else None
