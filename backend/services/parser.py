import datetime
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


async def get_html(url: str, session: aiohttp.ClientSession = None, bot: Bot=None):
    cached_html = _get_cached_html(url)
    if cached_html:
        logger.debug(f"HTML cache hit for {url}")
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
            try:
                async with session.get(SCRAPER_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    logger.info(f"ScraperAPI request to {url} - Status: {response.status} - Used API name: {key.name}")
                    if response.status == 200:
                        html_text = await response.text()
                        await key_pool.report_success(key, bot)
                        _set_cached_html(url, html_text)
                        return html_text

                    error_text = f"{response.status}: {(await response.text())[:300]}"

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
                return None
            except Exception as e:
                logger.error(f"Network error for {url}: {e}")
                await key_pool.report_failure(key, f"Network error: {e}", bot)
                return None

        logger.critical("Too many attempts.")
        return None
    finally:
        if close_session:
            await session.close()


async def get_updates(bot: Bot):
    """
    Парсит главную страницу и возвращает список свежих серий.
    Возвращает None при ошибке сети/парсинга.
    """
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(URL_MAIN, session, bot)

        if html_text is None:
            return None

        soup = bs(html_text, 'html.parser')
        all_items = soup.find_all(class_='aw-item')

        fresh_updates = []

        for item in all_items:
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

                    rest_part = parts[1]
                    studio = "Unknown"
                    if '—' in rest_part:
                        studio = rest_part.split('—')[0].strip()
                    else:
                        studio = rest_part.strip()

                    fresh_updates.append({
                        'title': title,
                        'episode': episode_num,
                        'studio': studio,
                        'link': link,
                        'poster_url': poster_url
                    })

            except Exception as e:
                logger.warning(f"Error parsing item: {e}")
                continue

        return fresh_updates


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
                {'title': '...', 'link': '...', 'time': '...'},
                ...
            ]
        },
        ...
    ]
    """
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(URL_MAIN, session, bot)

        if not html_text:
            return None

        soup = bs(html_text, 'html.parser')
        schedule_widget = soup.find(class_='anime-widget')

        if not schedule_widget:
            return []

        schedule_days = []

        # Находим все блоки дней
        day_blocks = schedule_widget.find_all(class_='aw-day')

        for day_block in day_blocks:
            try:
                # 1. Заголовок дня (День + Дата)
                day_name_tag = day_block.find(class_='schedule-day')
                day_date_tag = day_block.find(class_='schedule-date')

                day_name = day_name_tag.get_text(strip=True) if day_name_tag else "???"
                day_date = day_date_tag.get_text(strip=True) if day_date_tag else ""

                full_date_str = f"{day_name} {day_date}".strip()

                # 2. Список аниме в этот день
                items = []
                anime_nodes = day_block.find_all(class_='aw-item')

                for anime in anime_nodes:
                    raw_link = anime.get('href')
                    link = clean_link(raw_link)

                    title = anime.find(class_='aw-name').get_text(strip=True)
                    image_tag = anime.find('img')
                    poster_url = clean_asset_url(image_tag.get('src')) if image_tag else ""

                    time_tag = anime.find(class_='aw-meta__episode-time')
                    time_str = time_tag.get_text(strip=True) if time_tag else ""

                    items.append({
                        'title': title,
                        'link': link,
                        'time': time_str,
                        'poster_url': poster_url
                    })

                if items:
                    schedule_days.append({
                        'date_str': full_date_str,
                        'items': items
                    })

            except Exception as e:
                logger.warning(f"Error parsing schedule day: {e}")
                continue

        return schedule_days


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

        return info

    except Exception as e:
        logger.error(f"Error parsing anime details {url}: {e}")
        return None


async def get_filtered(vo: str, bot: Bot):
    """
    Возвращает СПИСОК аниме (list of dict), отфильтрованный по озвучке.
    Возвращает None, если произошла ошибка при получении данных.
    """
    updates = await get_updates(bot)

    if updates is None:
        return None

    filtered_anime = []
    for anime in updates:
        anime_studio_clean = anime['studio'].strip().lower()
        vo_clean = vo.strip().lower()

        if vo == "Все" or vo_clean in anime_studio_clean or vo_clean == anime_studio_clean:
            filtered_anime.append(anime)

    return filtered_anime
