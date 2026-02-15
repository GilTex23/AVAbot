import aiohttp
from bs4 import BeautifulSoup as bs
import logging
import urllib.parse
import asyncio
import random

URL_MAIN = 'https://animego.me/'
URL_SEARCH = 'https://animego.me/search/all?q='

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0'
}

logger = logging.getLogger(__name__)


async def get_html(url: str, session: aiohttp.ClientSession = None):
    """Получает HTML с сохранением кук"""
    close_session = False

    if session is None:
        # Создаем сессию с куками
        session = aiohttp.ClientSession(headers=HEADERS)
        close_session = True

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
            logger.info(f"Request to {url} - Status: {response.status}")

            if response.status != 200:
                try:
                    error_text = await response.text()
                    logger.error(f"Status {response.status} for {url}")
                    logger.error(f"Response headers: {dict(response.headers)}")
                    logger.error(f"Response text: {error_text[:500]}")  # первые 500 символов
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


async def get_updates():
    """
    Парсит главную страницу и возвращает список свежих серий.
    """
    # Создаем сессию для сохранения кук между запросами
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Добавляем небольшую задержку перед первым запросом
        await asyncio.sleep(random.uniform(1, 3))

        html_text = await get_html(URL_MAIN, session)
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

                    await asyncio.sleep(random.uniform(0.1, 0.3))

            except Exception as e:
                logger.warning(f"Error parsing item: {e}")
                continue

        return fresh_updates


async def search_anime(query: str):
    """Поиск аниме (для функционала подписки)"""
    encoded_query = urllib.parse.quote(query)
    url = f"{URL_SEARCH}{encoded_query}"

    # Создаем сессию для сохранения кук
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        await asyncio.sleep(random.uniform(1, 2))

        html_text = await get_html(url, session)

        if not html_text:
            return []

        soup = bs(html_text, 'html.parser')
        results = []

        # Логика поиска зависит от верстки страницы поиска.
        # Обычно это .media-body или .animes-list-item
        content_divs = soup.find_all('div', class_='media-body')

        for item in content_divs:
            try:
                link_tag = item.find('a')
                if not link_tag:
                    continue

                href = link_tag.get('href')
                full_link = href if href.startswith('http') else 'https://animego.me' + href
                title = link_tag.get_text(strip=True)

                # Пытаемся найти номер последней серии в результатах поиска
                last_ep = "0"

                # Добавляем задержку
                await asyncio.sleep(random.uniform(0.1, 0.2))

                results.append({'title': title, 'url': full_link, 'last_ep': last_ep})
            except Exception as e:
                logger.warning(f"Error parsing search result: {e}")
                continue

        return results[:10]


# Дополнительная функция для проверки доступности сайта
async def check_site_availability():
    """Проверяет, доступен ли сайт"""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        try:
            async with session.get(URL_MAIN, timeout=aiohttp.ClientTimeout(total=10)) as response:
                logger.info(f"Site check - Status: {response.status}")
                logger.info(f"Cookies: {list(session.cookie_jar)}")

                if response.status == 200:
                    return True
                elif response.status == 500:
                    logger.error("Site returned 500 error - likely blocked by DDOS-Guard")
                    return False
                else:
                    logger.warning(f"Unexpected status: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Site check failed: {e}")
            return False