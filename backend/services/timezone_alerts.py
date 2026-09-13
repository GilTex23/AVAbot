"""
Уведомления админам о незнакомых подписях часового пояса на главной AnimeGO.

AnimeGO подписывает время поясом IP прокси («16:00 (Самара)»). Если подписи нет в TIMEZONE_LABELS,
время с такой страницы не используется, а админ получает сообщение о каждой такой загрузке:
с примерами со страницы, смещением, вычисленным по сериям с уже известным временем выхода,
и готовой строкой для MANUAL_LABELS в scripts/generate_timezone_labels.py.
Страны и города из CLDR уже есть в сгенерированном словаре, так что сюда попадают только подписи, которых нет в CLDR.
"""
import datetime
import hashlib
import html
import logging
from collections import Counter, deque
from zoneinfo import ZoneInfo

from aiogram import Bot

from database import requests as db
from services.notifier import notify_admins
from services.timezone_labels import AMBIGUOUS_TIMEZONE_LABELS, TIMEZONE_LABELS

logger = logging.getLogger(__name__)

MSK = ZoneInfo("Europe/Moscow")
# Прокси у ScraperAPI в основном российские — их пояса предлагаем первыми
PREFERRED_ZONES = (
    "Europe/Kaliningrad", "Europe/Moscow", "Europe/Samara", "Asia/Yekaterinburg", "Asia/Omsk",
    "Asia/Novosibirsk", "Asia/Krasnoyarsk", "Asia/Irkutsk", "Asia/Yakutsk", "Asia/Vladivostok",
    "Asia/Magadan", "Asia/Kamchatka",
)

# Одна и та же страница разбирается несколько раз из кэша — это не новый случай
_reported_pages: deque[str] = deque(maxlen=50)


def format_offset(offset: datetime.timedelta) -> str:
    minutes = int(offset.total_seconds() // 60)
    hours, rest = divmod(abs(minutes), 60)
    return f"UTC{'+' if minutes >= 0 else '-'}{hours}" + (f":{rest:02d}" if rest else "")


def zones_with_offset(offset: datetime.timedelta, at: datetime.datetime) -> list[str]:
    def matches(zone: str) -> bool:
        return ZoneInfo(zone).utcoffset(at) == offset

    preferred = [zone for zone in PREFERRED_ZONES if matches(zone)]
    others = sorted({zone for zone in TIMEZONE_LABELS.values() if zone.startswith(("Europe/", "Asia/")) and matches(zone)})
    return (preferred + [zone for zone in others if zone not in preferred])[:4]


async def guess_offset(page_airings: list[tuple[str, int, datetime.datetime]]) -> datetime.timedelta | None:
    """
    page_airings: (url, серия, время со страницы, прочитанное как UTC).
    Сверяет его с уже известным временем выхода тех же серий и возвращает самое частое смещение.
    """
    if not page_airings:
        return None
    known = {
        (airing.anime_url, airing.episode): airing.air_at
        for airing in await db.get_episode_airings({url for url, _, _ in page_airings})
    }

    offsets = Counter()
    for url, episode, local_as_utc in page_airings:
        air_at = known.get((url, episode))
        if air_at is None:
            continue
        minutes = round((local_as_utc - air_at).total_seconds() / 60 / 15) * 15
        # «Сегодня»/«Завтра» читались по дате UTC, поэтому разница может уехать на сутки — сворачиваем в [-11 ч, +13 ч)
        offsets[(minutes + 11 * 60) % (24 * 60) - 11 * 60] += 1

    if not offsets:
        return None
    return datetime.timedelta(minutes=offsets.most_common(1)[0][0])


async def report_unknown_timezone(
    bot: Bot | None,
    label: str,
    html_text: str,
    examples: list[str],
    page_airings: list[tuple[str, int, datetime.datetime]],
):
    """Пишет админам о странице с незнакомой подписью пояса (по одному разу на загруженную страницу)"""
    digest = hashlib.sha1(html_text.encode("utf-8")).hexdigest()
    if digest in _reported_pages:
        return
    _reported_pages.append(digest)
    if bot is None:
        return

    try:
        offset = await guess_offset(page_airings)
    except Exception as e:
        logger.error(f"Failed to guess offset for timezone label '{label}': {e}")
        offset = None

    now = datetime.datetime.now(datetime.timezone.utc)
    safe_label = html.escape(label)
    if label in AMBIGUOUS_TIMEZONE_LABELS:
        header = f"🕒 Неоднозначный часовой пояс на главной AnimeGO: «{safe_label}» — за этой подписью пояса с разными смещениями."
    else:
        header = f"🕒 Незнакомый часовой пояс на главной AnimeGO: «{safe_label}»."

    lines = [
        header,
        "",
        "Время с этой загрузки не использовано: выходы серий записаны по времени опроса (±20 мин), "
        "расписание возьмётся со следующей загрузки.",
        "",
    ]
    if examples:
        lines.append("Со страницы: " + ", ".join(f"«{html.escape(example)}»" for example in examples) + ".")
    lines.append(f"Загружено в {now.astimezone(MSK):%H:%M} МСК.")

    zone = None
    if offset is not None:
        zones = zones_with_offset(offset, now)
        zone = zones[0] if zones else None
        lines.append(
            f"По сериям с уже известным временем выхода это {format_offset(offset)}"
            + (f": {', '.join(zones)}." if zones else ".")
        )
        lines.append("Совпадает только текущее смещение — проверьте, что у выбранного пояса те же переходы на летнее время.")
    else:
        lines.append("Смещение определить не удалось: по сериям на этой странице ещё нет истории.")

    lines += [
        "",
        "Чтобы бот понимал эту подпись, добавьте в MANUAL_LABELS (backend/scripts/generate_timezone_labels.py) и пересоберите словарь:",
        f"<code>{html.escape(repr(label), quote=False)}: {html.escape(repr(zone or 'Регион/Город'), quote=False)},</code>",
    ]

    try:
        await notify_admins(bot, "\n".join(lines), level="WARNING")
    except Exception as e:
        logger.error(f"Failed to notify admins about timezone label '{label}': {e}")
