"""
Озвучки: справочник студий с AnimeGO и фильтр ленты по любимым озвучкам.

Справочник пополняется сам — из ленты свежих серий и со страниц тайтлов. Списки в боте и мини-аппе
упорядочены по популярности: сколько серий озвучки было в ленте за POPULAR_DAYS дней и сколько на неё подписок.
Любимые озвучки хранятся списком названий; пустой список — все озвучки.
"""
import datetime
import logging
from collections import Counter

from database import requests as db

logger = logging.getLogger(__name__)

ALL_VOICEOVERS = "Все"
POPULAR_DAYS = 60
MAX_FAVORITES = 20


def _key(name: str | None) -> str:
    return (name or "").strip().lower()


def matches(voiceover: str, studio: str) -> bool:
    """Подходит ли серия из ленты к озвучке: «Все» — любая, иначе озвучка входит в название студии"""
    if voiceover == ALL_VOICEOVERS:
        return True
    voiceover_key, studio_key = _key(voiceover), _key(studio)
    return bool(voiceover_key) and (voiceover_key == studio_key or voiceover_key in studio_key)


def filter_updates(updates: list[dict], voiceovers: list[str] | None) -> list[dict]:
    """Серии ленты для списка озвучек; пустой список — все серии"""
    if not voiceovers:
        return list(updates)
    return [item for item in updates if any(matches(voiceover, item.get("studio") or "") for voiceover in voiceovers)]


def studios_in(updates: list[dict]) -> list[dict]:
    """Озвучки, которые сейчас есть в ленте: [{name, count}], самые частые первыми"""
    counts = Counter(item["studio"] for item in updates if item.get("studio"))
    return [{"name": name, "count": count} for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].lower()))]


def clean_names(names) -> list[str]:
    """Названия без пробелов по краям, пустых, «Все» и повторов (без учёта регистра), в исходном порядке"""
    result, seen = [], set()
    for name in names or []:
        if not isinstance(name, str):
            continue
        name = name.strip()
        if not name or name == ALL_VOICEOVERS or _key(name) in seen:
            continue
        seen.add(_key(name))
        result.append(name)
    return result


def describe(voiceovers: list[str], limit: int = 3) -> str:
    """«AniLiberty, AniDUB и ещё 2» или «Все озвучки»"""
    if not voiceovers:
        return "Все озвучки"
    if len(voiceovers) <= limit:
        return ", ".join(voiceovers)
    return f"{', '.join(voiceovers[:limit])} и ещё {len(voiceovers) - limit}"


async def remember(names) -> None:
    """Записывает встреченные озвучки в справочник; ошибка не мешает основной работе"""
    names = clean_names(names)
    if not names:
        return
    try:
        await db.touch_voiceovers(names)
    except Exception as e:
        logger.error(f"Failed to remember voiceovers {names}: {e}")


async def catalog() -> list[dict]:
    """Справочник озвучек, популярные первыми: [{id, name, releases, subscriptions, last_seen_at}]"""
    since = datetime.datetime.utcnow() - datetime.timedelta(days=POPULAR_DAYS)
    return await db.get_voiceover_catalog(since)


async def validate_favorites(names) -> list[str]:
    """Оставляет только озвучки из справочника; ValueError — если список слишком длинный или есть незнакомые"""
    cleaned = clean_names(names)
    if len(cleaned) > MAX_FAVORITES:
        raise ValueError(f"Можно выбрать не больше {MAX_FAVORITES} озвучек")
    known = await db.get_voiceover_names(cleaned)
    unknown = [name for name in cleaned if name not in known]
    if unknown:
        raise ValueError(f"Неизвестные озвучки: {', '.join(unknown)}")
    return cleaned
