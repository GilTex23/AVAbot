"""
Оценки тайтла с AnimeGO, Shikimori и YummyAnime — только из того, что бот уже сохранил, без отдельных запросов.

- AnimeGO — со страницы тайтла (она и так загружается при подписке, выборе озвучки и еженедельной проверке);
- Shikimori — у тайтлов, сопоставленных с Shikimori, и у тайтлов YummyAnime (их API отдаёт id на Shikimori);
- YummyAnime — собственная оценка из их API.
Тайтлы разных сайтов связаны через id на Shikimori: к подписке AnimeGO подтягивается оценка YummyAnime и наоборот,
если второй тайтл боту уже встречался.
"""
from database import requests as db

MATCHED_STATUSES = ("matched", "manual")
LABELS = {"animego": "AnimeGO", "shikimori": "Shikimori", "yummy": "YummyAnime"}


def _item(source: str, value, votes=None, url=None) -> dict | None:
    if not value:
        return None
    return {"source": source, "value": round(float(value), 2), "votes": votes or None, "url": url}


def _compose(animego=None, shikimori=None, yummy=None, animego_page: dict | None = None) -> list[dict]:
    """animego/shikimori/yummy — строки anime_titles/shikimori_animes/yummy_titles; animego_page — оценка со свежей страницы"""
    items = [
        _item("animego", animego_page["rating"], animego_page.get("rating_votes"), animego_page.get("url"))
        if animego_page and animego_page.get("rating")
        else _item("animego", animego.rating, animego.rating_votes, animego.url) if animego else None,
        _item("shikimori", shikimori.score, None, shikimori.url) if shikimori else None,
        _item("yummy", yummy.rating, yummy.rating_votes, yummy.url) if yummy else None,
    ]
    return [item for item in items if item]


def _matched_shikimori_id(title) -> int | None:
    return title.shikimori_id if title is not None and title.shikimori_status in MATCHED_STATUSES else None


async def for_subscriptions(subscriptions) -> dict[int, list[dict]]:
    """{id подписки: [оценки]}; порядок — AnimeGO, Shikimori, YummyAnime"""
    animego_urls = {sub.anime_url for sub in subscriptions if sub.source != "yummy"}
    yummy_ids = {int(sub.source_id) for sub in subscriptions if sub.source == "yummy" and str(sub.source_id or "").isdigit()}

    titles = await db.get_titles_by_urls(animego_urls)
    yummy_titles = await db.get_yummy_titles(yummy_ids)
    shikimori_of_animego = {sid for title in titles.values() if (sid := _matched_shikimori_id(title))}
    shikimori_of_yummy = {title.shikimori_id for title in yummy_titles.values() if title.shikimori_id}

    shikimori = await db.get_shikimori_animes(shikimori_of_animego | shikimori_of_yummy)
    animego_by_shikimori = await db.get_titles_by_shikimori_ids(shikimori_of_yummy)
    yummy_by_shikimori = await db.get_yummy_titles_by_shikimori_ids(shikimori_of_animego)

    result = {}
    for sub in subscriptions:
        if sub.source == "yummy":
            yummy = yummy_titles.get(int(sub.source_id)) if str(sub.source_id or "").isdigit() else None
            sid = yummy.shikimori_id if yummy else None
            result[sub.id] = _compose(animego_by_shikimori.get(sid), shikimori.get(sid), yummy)
        else:
            animego = titles.get(sub.anime_url)
            sid = _matched_shikimori_id(animego)
            result[sub.id] = _compose(animego, shikimori.get(sid), yummy_by_shikimori.get(sid))
    return result


async def for_animego_title(url: str, page: dict | None = None) -> list[dict]:
    """Оценки тайтла AnimeGO; page — только что разобранная страница (её оценка свежее сохранённой)"""
    title = await db.get_title_by_url(url)
    sid = _matched_shikimori_id(title)
    shikimori = (await db.get_shikimori_animes({sid})).get(sid) if sid else None
    yummy = (await db.get_yummy_titles_by_shikimori_ids({sid})).get(sid) if sid else None
    animego_page = {**page, "url": url} if page else None
    return _compose(title, shikimori, yummy, animego_page)


async def for_yummy_title(row: dict) -> list[dict]:
    """Оценки тайтла YummyAnime по строке yummy_titles (dict из API)"""
    sid = row.get("shikimori_id")
    shikimori = (await db.get_shikimori_animes({sid})).get(sid) if sid else None
    animego = (await db.get_titles_by_shikimori_ids({sid})).get(sid) if sid else None
    items = _compose(animego, shikimori)
    own = _item("yummy", row.get("rating"), row.get("rating_votes"), row.get("url"))
    return items + [own] if own else items


def describe(items: list[dict]) -> str:
    """«⭐ AnimeGO 9.0 · Shikimori 9.05 · YummyAnime 9.3» или пустая строка"""
    if not items:
        return ""
    return "⭐ " + " · ".join(f"{LABELS[item['source']]} {item['value']:g}" for item in items)
