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
                    return None
                return await response.text()
        except Exception as e:
            logger.error(f"Network error: {e}")
            return None


async def get_updates():
    """
    Возвращает список словарей:
    [{'title': str, 'episode': str, 'studio': str, 'link': str}, ...]
    """
    html_text = await get_html(URL_MAIN)
    if not html_text:
        return []

    soup = bs(html_text, 'html.parser')
    all_items = soup.find_all(class_='aw-item text-decoration-none text-reset mw-0')

    fresh_updates = []

    for item in all_items:
        meta_div = item.find(class_='aw-meta')
        if not meta_div:
            continue

        meta_text = meta_div.get_text(" ", strip=True)

        # Фильтр: наличие точки означает наличие озвучки
        if '·' in meta_text:
            link = item.get('href')
            if not link.startswith('http'):
                link = 'https://animego.me' + link

            title = item.find(class_='aw-name').get_text(strip=True)

            # Парсинг строки "Серия X · Озвучка — Время"
            try:
                parts = meta_text.split('·')
                episode_num = parts[0].strip()  # "Серия 3"

                rest_part = parts[1]
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
                logger.warning(f"Error parsing meta text '{meta_text}': {e}")
                continue

    return fresh_updates


async def search_anime(query: str):
    """
    Поиск аниме.
    Возвращает список: [{'title': 'Название', 'url': 'ссылка', 'last_ep': '10'}]
    """
    encoded_query = urllib.parse.quote(query)
    url = f"{URL_SEARCH}{encoded_query}"

    html_text = await get_html(url)
    if not html_text:
        return []

    soup = bs(html_text, 'html.parser')

    results = []
    # Внимание: классы на странице поиска могут отличаться от главной
    # Обычно это 'animes-list-item' или похожие в результатах поиска
    items = soup.find_all(class_='row')

    # Это примерная логика, так как точную верстку поиска нужно смотреть по факту
    # Постараемся найти блоки с ссылками на аниме

    # Ищем карточки (обычно h5 или .h5 внутри div)
    content_divs = soup.find_all('div', class_='media-body')

    for item in content_divs:
        try:
            link_tag = item.find('a')
            if not link_tag:
                continue

            href = link_tag.get('href')
            title = link_tag.get_text(strip=True)

            # Попробуем найти текущую серию (часто в span или div рядом)
            # Если не найдем, ставим 0
            last_ep = "0"
            meta_info = item.find_next(class_='anime-year')  # Пример
            if meta_info:
                # логика извлечения
                pass

            results.append({
                'title': title,
                'url': href if href.startswith('http') else 'https://animego.me' + href,
                'last_ep': last_ep
            })
        except Exception as e:
            logger.warning(f"Error parsing search item: {e}")
            continue

    return results[:10]  # Возвращаем топ-10
