import datetime
import re
from collections import Counter
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import aiohttp
from bs4 import BeautifulSoup as bs
import logging
import urllib.parse
import asyncio
import time
import config
from aiogram import Bot
from services.notifier import notify_admins
from services.scraper_keys import key_pool, STATUS_EXHAUSTED, STATUS_INVALID
from services import stats, timezone_alerts, voiceovers
from services.timezone_labels import TIMEZONE_LABELS
from utils.antispam import AntiSpamNotify


SCRAPER_API_URL = 'https://api.scraperapi.com/'

URL_MAIN = 'https://animego.me/'
URL_SEARCH = 'https://animego.me/search/all?q='

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0'
}

logger = logging.getLogger(__name__)

antispam = AntiSpamNotify(logger)

_HTML_CACHE = {}


def _get_cached_html(url: str):
    cached = _HTML_CACHE.get(url)
    if not cached:
        return None

    expires_at, html_text = cached
    if expires_at <= time.monotonic():
        _HTML_CACHE.pop(url, None)
        return None

    return html_text


def _set_cached_html(url: str, html_text: str):
    ttl = getattr(config, "ANIMEGO_CACHE_TTL_SECONDS", 300)
    if ttl <= 0 or not html_text:
        return

    _HTML_CACHE[url] = (time.monotonic() + ttl, html_text)


def clean_link(link: str) -> str:
    if not link: return link
    if not link.startswith('http'):
        link = 'https://animego.me' + link
    return link.split('#')[0].rstrip('/')


def clean_asset_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://animego.me" + url
    return url


def parse_total_episodes(episodes_text: str | None) -> int | None:
    """
    Общее число серий из поля «Эпизоды» на AnimeGO:
    '6 / 13' -> 13, '11 / ?' -> None, '14' -> 14 (у вышедшего тайтла AnimeGO пишет одно число)
    """
    if not episodes_text:
        return None
    total_str = episodes_text.split('/')[-1].strip()
    return int(total_str) if total_str.isdigit() else None


async def _notify_no_keys(bot: Bot):
    antispam.failed_requests += 1
    logger.critical(f"All your API keys are exhausted or invalid!\nPlease check logs and your API keys.\nFailed requests until restart: {antispam.failed_requests}")
    if not antispam.is_notified():
        await notify_admins(
            bot,
            "Все API ключи ScraperAPI исчерпаны или недействительны!\n\n"
            "Парсинг аниме временно недоступен.\n"
            "Добавьте или включите ключи в админке мини-аппа (Настройки → Администрирование).",
            level="CRITICAL"
        )
        antispam.set_notify_timestamp()


async def _record_attempt(dimension: str, outcome: str, started: float, status: str | None = None):
    """Статистика одной попытки через ScraperAPI: исход по источнику, причина ошибки и время ответа"""
    rows = [
        (f"scraper.{outcome}", dimension, 1),
        ("scraper.latency_ms", "", int((time.monotonic() - started) * 1000)),
        ("scraper.latency_count", "", 1),
    ]
    if status:
        rows.append(("scraper.failed_status", status, 1))
    await stats.increment_many(rows)


async def get_html(url: str, session: aiohttp.ClientSession = None, bot: Bot=None):
    # Для статистики: кто попросил страницу (чекер, мини-апп, бот...) и какую — главную или тайтла
    page_kind = "home" if url.rstrip('/') == URL_MAIN.rstrip('/') else "anime"
    stats_dimension = f"{stats.request_source.get()}:{page_kind}"

    cached_html = _get_cached_html(url)
    if cached_html:
        logger.debug(f"HTML cache hit for {url}")
        await stats.increment("cache.hit", stats_dimension)
        return cached_html

    close_session = False

    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        if getattr(config, "ANIMEGO_DIRECT_ENABLED", True):
            try:
                direct_timeout = aiohttp.ClientTimeout(
                    total=getattr(config, "ANIMEGO_DIRECT_TIMEOUT_SECONDS", 5)
                )
                async with session.get(url, headers=HEADERS, timeout=direct_timeout) as response:
                    logger.info(f"Direct request to {url} - Status: {response.status}")
                    if response.status == 200:
                        html_text = await response.text()
                        _set_cached_html(url, html_text)
                        return html_text

                    if response.status not in (403, 429, 500, 502, 503, 504):
                        error_text = await response.text()
                        logger.warning(
                            f"Direct request to {url} returned {response.status}. "
                            f"Response text: {error_text[:300]}"
                        )
            except asyncio.TimeoutError:
                logger.warning(f"Direct request timeout for {url}; trying ScraperAPI")
            except Exception as e:
                logger.warning(f"Direct request error for {url}: {e}; trying ScraperAPI")

        tried_keys: set[int] = set()
        attempt = 1
        while attempt <= 7:
            key = key_pool.pick(exclude=tried_keys)
            if key is None:
                await _notify_no_keys(bot)
                return None

            params = {
                'api_key': key.api_key,
                'url': url.strip(),
                'device_type': 'desktop',
                'country_code': 'ru'
            }
            started = time.monotonic()
            try:
                # ScraperAPI сам повторяет запрос к сайту до ~60 с, поэтому короткий таймаут обрывает удачные запросы
                timeout = aiohttp.ClientTimeout(total=getattr(config, "SCRAPER_API_TIMEOUT_SECONDS", 70))
                async with session.get(SCRAPER_API_URL, params=params, timeout=timeout) as response:
                    logger.info(f"ScraperAPI request to {url} - Status: {response.status} - Used API name: {key.name}")
                    if response.status == 200:
                        html_text = await response.text()
                        await key_pool.report_success(key, bot)
                        await _record_attempt(stats_dimension, "success", started)
                        _set_cached_html(url, html_text)
                        return html_text

                    error_text = f"{response.status}: {(await response.text())[:300]}"
                await _record_attempt(stats_dimension, "failed", started, str(response.status))

                if response.status == 401:
                    logger.error(f"An unauthorized request. Please make sure that your API key \"{key.name}\" is valid.")
                    await key_pool.report_failure(key, error_text, bot, status=STATUS_INVALID)
                    tried_keys.add(key.id)
                elif response.status == 403:
                    logger.error(f"API limit exceeded - API Name: {key.name}")
                    await key_pool.report_failure(key, error_text, bot, status=STATUS_EXHAUSTED)
                    tried_keys.add(key.id)
                    attempt += 1
                elif response.status == 500:
                    logger.error(f"Request failed. It's worth checking the URL - Attempt {attempt}")
                    await key_pool.report_failure(key, error_text, bot)
                    attempt += 1
                    await asyncio.sleep(1)
                elif response.status == 429:
                    logger.error(f"To many concurrent requests - Attempt {attempt}")
                    await key_pool.report_failure(key, error_text, bot)
                    attempt += 1
                    await asyncio.sleep(0.3)
                else:
                    # 404 (страницы нет), 400 (кривой запрос) и прочее повтор не исправит
                    logger.error(f"ScraperAPI request to {url} failed. Response: {error_text}")
                    await key_pool.report_failure(key, error_text, bot)
                    return None

            except asyncio.TimeoutError:
                logger.error(f"Timeout error for {url}")
                await key_pool.report_failure(key, "Timeout", bot)
                await _record_attempt(stats_dimension, "timeout", started, "timeout")
                return None
            except Exception as e:
                logger.error(f"Network error for {url}: {e}")
                await key_pool.report_failure(key, f"Network error: {e}", bot)
                await _record_attempt(stats_dimension, "failed", started, "network")
                return None

        logger.critical("Too many attempts.")
        return None
    finally:
        if close_session:
            await session.close()


# AnimeGO показывает время в часовом поясе IP, с которого пришёл запрос, и подписывает его: «16:00 (Армения)».
# Прокси ScraperAPI каждый раз разные, поэтому пояс определяется по подписи на каждой странице,
# а в расписании время приводится к московскому.
MSK = ZoneInfo("Europe/Moscow")

USER_TIMEZONE_LABELS = {
    "Europe/Kaliningrad": "Калининград",
    "Europe/Moscow": "Москва",
    "Europe/Samara": "Самара",
    "Asia/Yekaterinburg": "Екатеринбург",
    "Asia/Omsk": "Омск",
    "Asia/Novosibirsk": "Новосибирск",
    "Asia/Krasnoyarsk": "Красноярск",
    "Asia/Irkutsk": "Иркутск",
    "Asia/Yakutsk": "Якутск",
    "Asia/Vladivostok": "Владивосток",
    "Asia/Magadan": "Магадан",
    "Asia/Kamchatka": "Камчатка",
}

MONTHS_GENITIVE = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
}
_TIME_RE = re.compile(r'(\d{1,2}):(\d{2})')
_DAY_MONTH_RE = re.compile(r'(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?', re.IGNORECASE)
_TZ_LABEL_RE = re.compile(r'\(([^()]+)\)\s*$')
_unknown_timezone_labels: set[str] = set()


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _to_utc_naive(value: datetime.datetime) -> datetime.datetime:
    return value.astimezone(datetime.timezone.utc).replace(tzinfo=None)


def _utc_naive_to(value: datetime.datetime, zone) -> datetime.datetime:
    return value.replace(tzinfo=datetime.timezone.utc).astimezone(zone)


def _page_timezone(soup) -> tuple[str | None, ZoneInfo | None]:
    """Подпись часового пояса страницы («Армения») и сам пояс; пояс None — если его не удалось определить однозначно"""
    labels = Counter(
        match.group(1).strip()
        for tag in soup.find_all(class_='aw-meta__episode-time')
        if (match := _TZ_LABEL_RE.search(tag.get_text(strip=True)))
    )
    if not labels:
        return None, None

    label = labels.most_common(1)[0][0]
    zone_name = TIMEZONE_LABELS.get(label)
    if zone_name is None:
        if label not in _unknown_timezone_labels:
            _unknown_timezone_labels.add(label)
            logger.warning(f"Unknown AnimeGO timezone label '{label}': times from such pages are not used")
        return label, None
    return label, ZoneInfo(zone_name)


def _page_zone(soup) -> ZoneInfo | None:
    return _page_timezone(soup)[1]


def _parse_day(text: str, now: datetime.datetime) -> datetime.date | None:
    """'Сегодня', 'Вчера', 'Завтра', '28 апреля' или '28 апреля 2025' -> дата (год без указания — ближайший к now)"""
    lowered = text.lower()
    if 'сегодня' in lowered:
        return now.date()
    if 'вчера' in lowered:
        return now.date() - datetime.timedelta(days=1)
    if 'завтра' in lowered:
        return now.date() + datetime.timedelta(days=1)

    match = _DAY_MONTH_RE.search(lowered)
    if not match or match.group(2) not in MONTHS_GENITIVE:
        return None
    day, month = int(match.group(1)), MONTHS_GENITIVE[match.group(2)]
    if match.group(3):
        return datetime.date(int(match.group(3)), month, day)

    candidates = []
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            candidates.append(datetime.date(year, month, day))
        except ValueError:
            continue
    return min(candidates, key=lambda candidate: abs(candidate - now.date())) if candidates else None


def _parse_local_datetime(day_text: str, time_text: str, zone, now: datetime.datetime) -> datetime.datetime | None:
    """Дата и время AnimeGO в поясе страницы -> naive UTC; без известного пояса — None"""
    if zone is None:
        return None
    day = _parse_day(day_text, now.astimezone(zone))
    time_match = _TIME_RE.search(time_text)
    if day is None or not time_match:
        return None
    local = datetime.datetime.combine(day, datetime.time(int(time_match.group(1)), int(time_match.group(2))), tzinfo=zone)
    return _to_utc_naive(local)


_EPISODE_TOKEN_RE = re.compile(r'(\d+)\s*-\s*(\d+)|\d+(?:\.\d+)?')


def parse_episode_list(text: str | None) -> list[int]:
    """
    Номера серий из подписи AnimeGO: 'Серия 11' -> [11], 'Серии 1, 7-8' -> [1, 7, 8], 'Серия 18 и 19' -> [18, 19].
    Дробные спешлы вроде 6.5 пропускаются.
    """
    episodes = set()
    for match in _EPISODE_TOKEN_RE.finditer(text or ''):
        if match.group(1):
            first, last = int(match.group(1)), int(match.group(2))
            if first <= last and last - first <= 100:
                episodes.update(range(first, last + 1))
        elif '.' not in match.group(0):
            episodes.add(int(match.group(0)))
    return sorted(episodes)


def max_episode_number(text: str | None) -> float:
    """Номер последней серии в подписи: 'Серии 1, 7-8' -> 8, 'Серия 6.5' -> 6.5, без номера -> 0"""
    episodes = parse_episode_list(text)
    if episodes:
        return float(episodes[-1])
    match = re.search(r'\d+(?:\.\d+)?', text or '')
    return float(match.group(0)) if match else 0.0


def _parse_updates(soup, now: datetime.datetime, zone) -> list:
    fresh_updates = []

    for item in soup.find_all(class_='aw-item'):
        try:
            meta_div = item.find(class_='aw-meta')
            if not meta_div: continue

            meta_text = meta_div.get_text(" ", strip=True)

            if '·' in meta_text:
                raw_link = item.get('href')
                link = clean_link(raw_link)

                title_tag = item.find(class_='aw-name')
                title = title_tag.get_text(strip=True) if title_tag else "Unknown"
                image_tag = item.find('img')
                poster_url = clean_asset_url(image_tag.get('src')) if image_tag else ""

                parts = meta_text.split('·')
                episode_num = parts[0].strip()

                # "AniLiberty — Сегодня, 11:10" (время в поясе страницы)
                rest_part = parts[1]
                released_at = None
                if '—' in rest_part:
                    studio, _, released_text = rest_part.partition('—')
                    studio = studio.strip()
                    released_at = _parse_local_datetime(released_text, released_text, zone, now)
                else:
                    studio = rest_part.strip()

                fresh_updates.append({
                    'title': title,
                    'episode': episode_num,
                    'studio': studio,
                    'link': link,
                    'poster_url': poster_url,
                    'released_at': released_at,
                })

        except Exception as e:
            logger.warning(f"Error parsing item: {e}")
            continue

    return fresh_updates


def _parse_schedule(soup, now: datetime.datetime, zone) -> list:
    schedule_widget = next(
        (widget for widget in soup.find_all(class_='anime-widget') if widget.find(class_='aw-day')), None
    )
    if not schedule_widget:
        return []

    schedule_days = []
    day_dates = []

    for day_block in schedule_widget.find_all(class_='aw-day'):
        try:
            # 1. Заголовок дня: день недели + дата ("28 апреля") или "Сегодня"/"Завтра"
            day_name_tag = day_block.find(class_='schedule-day')
            day_date_tag = day_block.find(class_='schedule-date')
            relative_tag = day_block.find(class_=['schedule-today', 'schedule-tomorrow'])

            day_name = day_name_tag.get_text(strip=True) if day_name_tag else "???"
            day_date = day_date_tag.get_text(strip=True) if day_date_tag else ""

            full_date_str = f"{day_name} {day_date}".strip()
            day_text = day_date or (relative_tag.get_text(strip=True) if relative_tag else "")

            # 2. Список аниме в этот день
            items = []
            for anime in day_block.find_all(class_='aw-item'):
                raw_link = anime.get('href')
                link = clean_link(raw_link)

                title = anime.find(class_='aw-name').get_text(strip=True)
                image_tag = anime.find('img')
                poster_url = clean_asset_url(image_tag.get('src')) if image_tag else ""

                time_tag = anime.find(class_='aw-meta__episode-time')
                time_str = time_tag.get_text(strip=True) if time_tag else ""

                # "Серия 4 (из 12) — 16:00 (Москва)" или "Серия 18 и 19 (из 56)"; у части тайтлов времени нет
                meta_div = anime.find(class_='aw-meta')
                meta_text = meta_div.get_text(" ", strip=True) if meta_div else ""
                total_tag = anime.find(class_='aw-meta__episode-total')
                totals = parse_episode_list(total_tag.get_text(strip=True)) if total_tag else []

                air_at = _parse_local_datetime(day_text, time_str, zone, now) if day_text and time_str else None
                if air_at is not None:
                    time_str = f"{_utc_naive_to(air_at, MSK):%H:%M} (Москва)"

                items.append({
                    'title': title,
                    'link': link,
                    'time': time_str,
                    'poster_url': poster_url,
                    'episodes': parse_episode_list(meta_text.split('—')[0].split('(')[0]),
                    'total_episodes': totals[-1] if totals else None,
                    'air_at': air_at,
                })

            if items:
                day_date = _parse_day(day_text, now.astimezone(zone)) if zone and day_text else None
                schedule_days.append({
                    'date_str': full_date_str,
                    'date': day_date.isoformat() if day_date else None,
                    'items': items
                })

        except Exception as e:
            logger.warning(f"Error parsing schedule day: {e}")
            continue

    if zone is not None:
        _regroup_by_date(schedule_days, MSK)
    return schedule_days


def _regroup_by_date(schedule_days: list, zone):
    """
    Раскладывает серии по дням по дате в поясе zone и сортирует по времени (серии без времени — в конце).

    Дни на странице — в поясе прокси (у дальневосточного IP вечерние серии по Москве попадают на следующий день),
    а пользователю нужны дни в его поясе. Серии, чья дата выпала за пределы недели на странице, убираются:
    в расписании этой недели их нет, а в историю они попали с прошлых загрузок.
    """
    day_by_date = {
        datetime.date.fromisoformat(day['date']): day for day in schedule_days if day.get('date')
    }
    if not day_by_date:
        return
    first_date, last_date = min(day_by_date), max(day_by_date)

    moves = []
    for day in schedule_days:
        for item in day['items']:
            if item['air_at'] is None:
                continue
            local_date = _utc_naive_to(item['air_at'], zone).date()
            if not first_date <= local_date <= last_date:
                moves.append((item, day, None))
                continue
            target = day_by_date.get(local_date)
            if target is not None and target is not day:
                moves.append((item, day, target))

    for item, source, target in moves:
        source['items'] = [other for other in source['items'] if other is not item]
        if target is not None:
            target['items'].append(item)

    for day in schedule_days:
        day['items'].sort(key=lambda item: (item['air_at'] is None, item['air_at'] or datetime.datetime.max))
    schedule_days[:] = [day for day in schedule_days if day['items']]


def zone_or_moscow(name: str | None) -> ZoneInfo:
    """Часовой пояс пользователя из настроек; по умолчанию и при ошибке — Москва"""
    try:
        return ZoneInfo(name) if name else MSK
    except (ZoneInfoNotFoundError, ValueError):
        return MSK


# def timezone_display_label(zone: ZoneInfo) -> str:
#     """Подпись пояса для времени в расписании: «Екатеринбург», если есть короткое русское название, иначе «UTC+5»"""
#     if zone.key == "Europe/Moscow":
#         return "Москва"
#     for label, zone_name in TIMEZONE_LABELS.items():
#         if zone_name == zone.key and "," not in label:
#             return label
#     return timezone_alerts.format_offset(datetime.datetime.now(zone).utcoffset())

def timezone_display_label(zone: ZoneInfo) -> str:
    """Подпись часового пояса пользователя."""
    label = USER_TIMEZONE_LABELS.get(zone.key)

    if label:
        return label

    return timezone_alerts.format_offset(
        datetime.datetime.now(zone).utcoffset()
    )


def localize_schedule(schedule_days: list, zone: ZoneInfo) -> list:
    """
    Расписание (по Москве) -> в поясе пользователя: время в подписи и разбивка по дням.
    Возвращает копию; кэшированный разбор страницы не меняется.
    """
    if zone.key == "Europe/Moscow":
        return schedule_days

    label = timezone_display_label(zone)
    localized = [
        {
            **day,
            'items': [
                {**item, 'time': f"{_utc_naive_to(item['air_at'], zone):%H:%M} ({label})"} if item['air_at'] else item
                for item in day['items']
            ],
        }
        for day in schedule_days
    ]
    _regroup_by_date(localized, zone)
    return localized


async def _get_home_soup(bot: Bot):
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(URL_MAIN, session, bot)
    if html_text is None:
        return None
    soup = bs(html_text, 'html.parser')

    label, zone = _page_timezone(soup)
    if label and zone is None:
        await _report_unknown_timezone(bot, label, soup, html_text)
    return soup


async def _report_unknown_timezone(bot: Bot, label: str, soup, html_text: str):
    """Готовит для админов примеры со страницы и время серий, прочитанное как UTC, — по нему угадывается смещение"""
    try:
        examples = []
        time_tag = soup.find(class_='aw-meta__episode-time')
        if time_tag:
            examples.append(time_tag.get_text(" ", strip=True))
        feed_meta = next((meta for meta in soup.find_all(class_='aw-meta') if '·' in meta.get_text()), None)
        if feed_meta and '—' in feed_meta.get_text():
            examples.append(feed_meta.get_text(" ", strip=True).rsplit('—', 1)[1].strip())

        as_utc = _parse_schedule(soup, _now_utc(), datetime.timezone.utc)
        page_airings = [
            (item['link'], episode, item['air_at'])
            for day in as_utc for item in day['items'] if item['air_at']
            for episode in item['episodes']
        ]
        await timezone_alerts.report_unknown_timezone(bot, label, html_text, examples, page_airings)
    except Exception as e:
        logger.error(f"Failed to report unknown timezone label '{label}': {e}")


async def get_home(bot: Bot):
    """
    Лента свежих серий и расписание с одного запроса главной страницы:
    {'updates': [...], 'schedule': [...], 'timezone': 'Москва', 'timezone_known': True} или None при ошибке сети.
    """
    soup = await _get_home_soup(bot)
    if soup is None:
        return None
    now = _now_utc()
    label, zone = _page_timezone(soup)
    return {
        'updates': _parse_updates(soup, now, zone),
        'schedule': _parse_schedule(soup, now, zone),
        'timezone': label,
        'timezone_known': zone is not None,
    }


async def get_updates(bot: Bot):
    """
    Парсит главную страницу и возвращает список свежих серий.
    Возвращает None при ошибке сети/парсинга.
    """
    soup = await _get_home_soup(bot)
    if soup is None:
        return None
    return _parse_updates(soup, _now_utc(), _page_zone(soup))


async def get_anime_info(url: str, bot: Bot):
    """
    Парсит страницу аниме и возвращает:
    {
        'status': str (Онгоинг/Вышел/Анонс),
        'type': str (Сериал/Фильм/...),
        'total_episodes': int or None (если '?')
    }
    """
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(url, session, bot)

    if not html_text:
        return None

    soup = bs(html_text, 'html.parser')
    info = {}

    try:
        def get_value(label_text):
            label_div = soup.find('div', string=lambda t: t and label_text in t, class_='text-body-tertiary')
            if label_div:
                value_div = label_div.find_next_sibling('div')
                if value_div:
                    return value_div.get_text(strip=True)
            return None

        # 1. Тип
        info['type'] = get_value("Тип")

        # 2. Статус
        info['status'] = get_value("Статус")

        # 3. Эпизоды ("6 / 13", "6 / ?" или просто "14" у вышедшего тайтла)
        info['total_episodes'] = parse_total_episodes(get_value("Эпизоды"))

        return info

    except Exception as e:
        logger.error(f"Error parsing anime info {url}: {e}")
        return None


async def get_schedule(bot: Bot):
    """
    Парсит виджет расписания.
    Возвращает список дней:
    [
        {
            'date_str': 'Понедельник 23 февраля',
            'items': [
                {'title': '...', 'link': '...', 'time': '16:00 (Москва)', 'episodes': [4], 'total_episodes': 12, 'air_at': datetime},
                ...
            ]
        },
        ...
    ]
    """
    soup = await _get_home_soup(bot)
    if soup is None:
        return None
    return _parse_schedule(soup, _now_utc(), _page_zone(soup))


async def get_anime_details(url: str, bot: Bot):
    """
    Парсит страницу аниме и возвращает полную информацию + список озвучек.
    """
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(url, session, bot)

    if not html_text:
        return None

    soup = bs(html_text, 'html.parser')
    info = {}

    try:
        def get_value(label_text):
            label_div = soup.find('div', string=lambda t: t and label_text in t, class_='text-body-tertiary')
            if label_div:
                value_div = label_div.find_next_sibling('div')
                if value_div:
                    return value_div
            return None

        type_div = get_value("Тип")
        info['type'] = type_div.get_text(strip=True) if type_div else None

        status_div = get_value("Статус")
        info['status'] = status_div.get_text(strip=True) if status_div else None

        episodes_div = get_value("Эпизоды")
        info['total_episodes'] = parse_total_episodes(episodes_div.get_text(strip=True) if episodes_div else None)

        voiceover_div = get_value("Озвучка")
        voiceovers_list = []

        if voiceover_div:
            links = voiceover_div.find_all('a', href=lambda h: h and '/anime/dubbing/' in h)
            for link in links:
                vo_name = link.get_text(strip=True)
                if vo_name:
                    voiceovers_list.append(vo_name)

        info['available_voiceovers'] = voiceovers_list
        await voiceovers.remember(voiceovers_list)

        return info

    except Exception as e:
        logger.error(f"Error parsing anime details {url}: {e}")
        return None


async def get_filtered(voiceover_names: list[str] | None, bot: Bot):
    """
    Свежие серии для списка озвучек (пустой список — все). None — если ленту не удалось получить.
    """
    updates = await get_updates(bot)
    if updates is None:
        return None
    return voiceovers.filter_updates(updates, voiceover_names)
