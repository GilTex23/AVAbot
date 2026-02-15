import aiohttp
from bs4 import BeautifulSoup as bs
import logging
import urllib.parse

URL_MAIN = 'https://animego.me/'
URL_SEARCH = 'https://animego.me/search/all?q='

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
}

logger = logging.getLogger(__name__)


async def get_html(url: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=HEADERS) as response:
                if response.status != 200:
                    logger.error(f"Status {response.status} for {url}")
                    logger.error(f"Response: {response}")
                    logger.error(f"Text: {response.text()}")
                    return None
                return await response.text()
        except Exception as e:
            logger.error(f"Network error: {e}")
            return None


async def get_updates():
    """
    Парсит главную страницу и возвращает список свежих серий.
    """
    html_text = await get_html(URL_MAIN)
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
                if not link.startswith('http'):
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


async def search_anime(query: str):
    """Поиск аниме (для функционала подписки)"""
    encoded_query = urllib.parse.quote(query)
    url = f"{URL_SEARCH}{encoded_query}"
    html_text = await get_html(url)

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
            if not link_tag: continue

            href = link_tag.get('href')
            full_link = href if href.startswith('http') else 'https://animego.me' + href
            title = link_tag.get_text(strip=True)

            # Пытаемся найти номер последней серии в результатах поиска (часто это спан с классом)
            last_ep = "0"
            # Здесь можно доработать парсинг количества серий, если оно есть в выдаче

            results.append({'title': title, 'url': full_link, 'last_ep': last_ep})
        except:
            continue

    return results[:10]