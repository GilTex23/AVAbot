"""
Тайтлы AnimeGO по числовому id и ссылки на них в бота.

Адрес тайтла заканчивается id: https://animego.me/anime/<длинное-название>-3484. Название бывает длиннее
лимита payload у /start (64 символа), поэтому в ссылку t.me/бот?start=a3484 кладётся только id,
а адрес и название берутся из таблицы anime_titles — она пополняется из ленты, расписания и подписок.
"""
import logging
import re

from database import requests as db

logger = logging.getLogger(__name__)

DEEP_LINK_PREFIX = "a"
_ID_RE = re.compile(r"-(\d+)/?$")
_PAYLOAD_RE = re.compile(rf"^{DEEP_LINK_PREFIX}(\d{{1,9}})$")


def anime_id(url: str | None) -> int | None:
    match = _ID_RE.search((url or "").split("#")[0].split("?")[0])
    return int(match.group(1)) if match else None


def deep_link_payload(url: str | None) -> str | None:
    """«a3484» для /start; None — если в адресе нет id"""
    found = anime_id(url)
    return f"{DEEP_LINK_PREFIX}{found}" if found is not None else None


def parse_payload(payload: str | None) -> int | None:
    match = _PAYLOAD_RE.match((payload or "").strip())
    return int(match.group(1)) if match else None


async def remember_meta(url: str, meta: dict) -> None:
    """Данные со страницы тайтла (parser.parse_title_meta) — для поиска на Shikimori"""
    url = (url or "").split("#")[0].rstrip("/")
    found = anime_id(url)
    title = (meta.get("title") or "").strip()
    if found is None or not title:
        return
    await db.upsert_title_meta({
        "id": found,
        "url": url,
        "title": title,
        "poster_url": meta.get("poster_url") or None,
        "alt_names": list(meta.get("alt_names") or []),
        "english_title": meta.get("english_title"),
        "kind": meta.get("kind"),
        "aired_on": meta.get("aired_on"),
        "episodes": meta.get("episodes"),
    })


async def remember(items) -> None:
    """items: словари с title, link и poster_url (как в ленте и расписании). Ошибка не мешает основной работе"""
    rows = []
    for item in items or []:
        url = (item.get("link") or "").split("#")[0].rstrip("/")
        found = anime_id(url)
        title = (item.get("title") or "").strip()
        if found is None or not title or title == "Unknown":
            continue
        rows.append({"id": found, "url": url, "title": title, "poster_url": item.get("poster_url") or None})
    if not rows:
        return
    try:
        await db.upsert_anime_titles(rows)
    except Exception as e:
        logger.error(f"Failed to remember anime titles: {e}")
