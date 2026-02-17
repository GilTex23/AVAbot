import datetime
import aiohttp
from bs4 import BeautifulSoup as bs
import logging
import urllib.parse
import asyncio
from random import choice
import config
from aiogram import Bot
from services.notifier import notify_admins
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


async def get_html(url: str, session: aiohttp.ClientSession = None, bot: Bot=None):
    """
    Получает HTML через ScraperAPI
    """
    close_session = False

    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    api_keys = config.SCRAPER_API_KEYS.copy()
    attempt = 1
    check_attempt = lambda x_: True if x_ <= 7 else False
    while True:
        try:
            if api_keys:
                api_key = choice(api_keys)
            else:
                antispam.failed_requests += 1
                logger.critical(f"All your API keys are exhausted or invalid!\nPlease check logs and your API keys.\nFailed requests until restart: {antispam.failed_requests}")
                if not antispam.is_notified():
                    await notify_admins(
                        bot,
                        "Все API ключи ScraperAPI исчерпаны или недействительны!\n\n"
                        "Парсинг аниме временно недоступен.\n"
                        "Необходимо добавить новые ключи в конфигурацию.",
                        level="CRITICAL"
                    )
                    antispam.set_notify_timestamp()
                return None
            params = {
                'api_key': api_key[1],
                'url': url.strip(),
                'device_type': 'desktop',
                'country_code': 'ru'
            }
            async with session.get(SCRAPER_API_URL, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                logger.info(f"ScraperAPI request to {url} - Status: {response.status} - Used API name: {api_key[0]}")
                if response.status == 200:
                    pass
                elif response.status in [500, 404, 429, 400, 403, 401]:
                    if check_attempt(attempt):
                        if response.status == 500:
                            logger.error(f"Request failed. It's worth checking the URL - Attempt {attempt}")
                            attempt += 1
                            await asyncio.sleep(1)
                            continue
                        elif response.status == 404:
                            logger.error(f"Bad Gateway - The requested page does not exist - Attempt {attempt}")
                            attempt += 5
                            await asyncio.sleep(0.3)
                            continue
                        elif response.status == 429:
                            logger.error(f"To many concurrent requests - Attempt {attempt}")
                            attempt += 1
                            await asyncio.sleep(0.3)
                            continue
                        elif response.status == 400:
                            logger.error(f"Error, invalid request. Make sure that your URL is entered correctly - Attempt {attempt}")
                            attempt += 5
                            await asyncio.sleep(0.5)
                        elif response.status == 403:
                            logger.error(f"API limit exceeded - API Name: {api_key[0]}")
                            api_keys.remove(api_key)
                            attempt += 1
                            await asyncio.sleep(0.1)
                            continue
                        elif response.status == 401:
                            logger.error(f"An unauthorized request. Please make sure that your API key \"{api_key[0]}\" is valid.")
                            api_keys.remove(api_key)
                            await asyncio.sleep(0.1)
                            continue
                else:
                    try:
                        error_text = await response.text()

                        logger.error(f"Response headers: {dict(response.headers)}")
                        logger.error(f"Response text: {error_text[:900]}")
                    except Exception as e:
                        logger.error(f"Failed to get error text: {e}")
                    return None

                return await response.text()

        except asyncio.TimeoutError:
            logger.error(f"Timeout error for {url}")
            return None
        except Exception as e:
            logger.error(f"Network error for {url}: {e}")
            return None
        finally:
            if close_session:
                await session.close()


async def get_updates(bot: Bot):
    """
    Парсит главную страницу и возвращает список свежих серий.
    """
    async with aiohttp.ClientSession() as session:
        html_text = await get_html(URL_MAIN, session, bot)
        if not html_text:
            return []

        soup = bs(html_text, 'html.parser')
        all_items = soup.find_all(class_='aw-item')

        fresh_updates = []

        for item in all_items:
            try:
                meta_div = item.find(class_='aw-meta')
                if not meta_div:
                    continue

                meta_text = meta_div.get_text(" ", strip=True)

                # Если есть точка, значит есть инфо об озвучке
                if '·' in meta_text:
                    link = item.get('href')
                    if link and not link.startswith('http'):
                        link = 'https://animego.me' + link

                    title_tag = item.find(class_='aw-name')
                    title = title_tag.get_text(strip=True) if title_tag else "Unknown"

                    # Парсинг строки "Серия 3 · AniStar — Сегодня, 15:30"
                    parts = meta_text.split('·')
                    episode_num = parts[0].strip()  # "Серия 3"

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
                        'link': link
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

        # 3. Эпизоды (формат "6 / 13" или "6 / ?").
        episodes_str = get_value("Эпизоды")
        info['total_episodes'] = None

        if episodes_str:
            parts = episodes_str.split('/')
            if len(parts) == 2:
                total_str = parts[1].strip()
                if total_str.isdigit():
                    info['total_episodes'] = int(total_str)

        return info

    except Exception as e:
        logger.error(f"Error parsing anime info {url}: {e}")
        return None


async def get_filtered(vo: str, bot: Bot):
    """
    Возвращает СПИСОК аниме (list of dict), отфильтрованный по озвучке.
    """
    updates = await get_updates(bot)

    filtered_anime = []
    for anime in updates:
        # Очистка названия студии от лишних пробелов для точного сравнения
        anime_studio_clean = anime['studio'].strip().lower()
        vo_clean = vo.strip().lower()

        if vo == "Все" or vo_clean in anime_studio_clean or vo_clean == anime_studio_clean:
            filtered_anime.append(anime)

    return filtered_anime


async def search_anime(query: str, bot: Bot):
    """Поиск аниме (для функционала подписки)"""
    encoded_query = urllib.parse.quote(query)
    url = f"{URL_SEARCH}{encoded_query}"

    async with aiohttp.ClientSession() as session:
        html_text = await get_html(url, session)

        if not html_text:
            return []

        soup = bs(html_text, 'html.parser')
        results = []

        # Логика поиска зависит от верстки страницы поиска
        content_divs = soup.find_all('div', class_='media-body')

        for item in content_divs:
            try:
                link_tag = item.find('a')
                if not link_tag:
                    continue

                href = link_tag.get('href')
                full_link = href if href.startswith('http') else 'https://animego.me' + href
                title = link_tag.get_text(strip=True)

                last_ep = "0"

                results.append({'title': title, 'url': full_link, 'last_ep': last_ep})
            except Exception as e:
                logger.warning(f"Error parsing search result: {e}")
                continue

        return results[:10]