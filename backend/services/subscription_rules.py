"""Когда на тайтл нельзя подписаться — одно правило для Telegram-бота и мини-аппа."""
from services.parser import max_episode_number


def subscription_block_reason(info: dict | None, last_episode: str | None) -> str | None:
    """
    Причина отказа или None, если подписаться можно.

    «Вышел» на AnimeGO означает конец показа оригинала, а озвучка может отставать на несколько серий,
    поэтому вышедший тайтл запрещаем, только если в выбранной озвучке уже есть последняя серия.
    """
    if not info:
        return None
    if info.get("type") and "Фильм" in info["type"]:
        return "Это фильм — новых серий у него не будет."

    total = info.get("total_episodes")
    released = bool(info.get("status")) and "Вышел" in info["status"]
    if released and total and max_episode_number(last_episode) >= total:
        return "Аниме уже вышло, и в этой озвучке доступны все серии."
    return None
