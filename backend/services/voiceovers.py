"""
Озвучки: справочник студий с AnimeGO и YummyAnime и фильтр ленты по любимым озвучкам.

Справочник пополняется сам — из лент свежих серий и со страниц тайтлов. Списки в боте и мини-аппе
упорядочены по популярности: сколько серий озвучки было в ленте за POPULAR_DAYS дней и сколько на неё подписок.
Любимые озвучки хранятся списком названий; пустой список — все озвучки.

Одна студия на разных сайтах пишется по-разному («RedHeadSound» и «Red Head Sound», «Озвучка Дубляж AniDUB»),
поэтому названия сравниваются по ключу без регистра, пробелов и знаков, а названия с YummyAnime сводятся
к уже известным в справочнике (canonical_names).
"""
import datetime
import logging
import re
import time
from collections import Counter

from database import requests as db

logger = logging.getLogger(__name__)

ALL_VOICEOVERS = "Все"
POPULAR_DAYS = 60
MAX_FAVORITES = 20


# Переименования и сокращения: ключ -> название, как его пишет AnimeGO
KNOWN_ALIASES = {
    "anilibria": "AniLiberty",
    "anidubonline": "AniDUB",
    "jam": "JAM CLUB",
}
_NON_ALNUM = re.compile(r"[\W_]+", re.UNICODE)
_CATALOG_TTL = 600
# (когда загружен по time.monotonic(), ключ -> название); None — не загружен.
# Не 0.0: сразу после загрузки системы monotonic() меньше TTL, и пустой кэш сошёл бы за свежий
_catalog_names: tuple[float | None, dict[str, str]] = (None, {})


def _key(name: str | None) -> str:
    return _NON_ALNUM.sub("", (name or "").lower().replace("ё", "е"))


def key(name: str | None) -> str:
    """Ключ для сравнения названий: «Red Head Sound» и «RedHeadSound» — одно и то же"""
    return _key(name)


def clean_source_name(raw: str | None) -> str:
    """
    Название озвучки с YummyAnime -> как на AnimeGO: «Озвучка AniDUB Online» -> «AniDUB Online»,
    «Озвучка Дубляж AniDUB» -> «AniDUB», «Субтитры SubVost» -> «SubVost.Subtitles»
    """
    name = " ".join((raw or "").split())
    for prefix in ("Озвучка ", "Дубляж "):
        if name.startswith(prefix) and len(name) > len(prefix):
            name = name[len(prefix):]
    if name.startswith("Субтитры ") and len(name) > len("Субтитры "):
        name = f"{name[len('Субтитры '):]}.Subtitles"
    return name


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
    global _catalog_names
    names = clean_names(names)
    if not names:
        return
    try:
        await db.touch_voiceovers(names)
        _catalog_names = (None, {})
    except Exception as e:
        logger.error(f"Failed to remember voiceovers {names}: {e}")


async def canonical_names(raw_names) -> dict[str, str]:
    """
    Сырые названия озвучек из другого источника -> названия из справочника:
    сначала известные переименования, потом совпадение по ключу, иначе очищенное название как есть
    """
    global _catalog_names
    loaded_at, by_key = _catalog_names
    if loaded_at is None or time.monotonic() - loaded_at > _CATALOG_TTL:
        try:
            by_key = {}
            for name in sorted(await db.get_all_voiceover_names()):
                by_key.setdefault(_key(name), name)
            _catalog_names = (time.monotonic(), by_key)
        except Exception as e:
            logger.error(f"Failed to load voiceover catalog: {e}")

    result = {}
    for raw in raw_names:
        cleaned = clean_source_name(raw)
        cleaned_key = _key(cleaned)
        result[raw] = KNOWN_ALIASES.get(cleaned_key) or by_key.get(cleaned_key) or cleaned
    return result


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
