from aiogram import Bot
from services import parser
from services.notifier import notify_admins
from utils.antispam import AntiSpamNotify
from database import requests as db
import logging
import re


logger = logging.getLogger(__name__)
antispam_updates = AntiSpamNotify(logger)


def extract_episode_number(ep_str: str) -> float:
    """Извлекает номер серии (float) из строки 'Серия 5' или 'Серия 6.5'"""
    if not ep_str: return 0
    # Ищем числа (включая дробные)
    match = re.search(r"(\d+(\.\d+)?)", ep_str)
    return float(match.group(1)) if match else 0


async def check_updates(bot: Bot):
    try:
        logger.debug("Starting anime check cycle...")

        updates = await parser.get_updates(bot)
        if not updates: return

        subscriptions = await db.get_all_subscriptions()
        if not subscriptions: return

        for sub in subscriptions:
            for update in updates:
                # Сравниваем URL
                if sub.anime_url == update['link']:

                    # Проверка озвучки
                    user_vo = sub.voiceover

                    studio_clean = update['studio'].strip().lower()
                    vo_clean = user_vo.strip().lower()

                    if user_vo == "Все" or vo_clean in studio_clean:

                        # Числовое сравнение серий
                        old_ep_num = extract_episode_number(sub.last_episode)
                        new_ep_num = int(extract_episode_number(update['episode']))

                        if new_ep_num > old_ep_num:
                            total_str = sub.total_episodes if sub.total_episodes else "?"

                            try:
                                await bot.send_message(
                                    chat_id=sub.user_id,
                                    text=(
                                        f"🔥 <b>Новая серия!</b>\n\n"
                                        f"📺 <b>{update['title']}</b>\n"
                                        f"🎬 <b>Серия:</b> {new_ep_num} из {total_str}\n"
                                        f"🎙 <b>Озвучка:</b> {update['studio']}\n\n"
                                        f"🔗 <a href='{update['link']}'>Смотреть</a>"
                                    ),
                                    parse_mode="HTML"
                                )
                                logger.info(f"Sent update to {sub.user_id}: {update['title']} ep {new_ep_num}")

                                # Обновляем последнюю серию
                                await db.update_sub_last_episode(sub.id, update['episode'])

                                # Проверяем, не последняя ли это серия
                                if sub.total_episodes and new_ep_num >= sub.total_episodes:
                                    await bot.send_message(
                                        sub.user_id,
                                        f"🏁 Аниме <b>{update['title']}</b> ({user_vo}) завершено! Удаляю из подписок."
                                    )
                                    await db.delete_subscription(sub.id)
                                    logger.info(f"Anime finished and removed: {sub.anime_title}")

                            except Exception as e:
                                logger.error(f"Failed to send to {sub.user_id}: {e}")
    except Exception as e:
        antispam_updates.failed_requests += 1
        logger.error(f"Checker updates error: {e}")
        if not antispam_updates.is_notified():
            await notify_admins(
                bot,
                f"Failed requests: {antispam_updates.failed_requests}\nОшибка в Checker Updates:\n<code>{str(e)}</code>",
                level="ERROR"
            )
            antispam_updates.set_notify_timestamp()


async def check_missing_episodes_info(bot: Bot):
    """
    Фоновая задача: раз в день проверяет аниме, у которых total_episodes is NULL
    """
    try:
        logger.info("Starting missing episodes check...")
        subscriptions = await db.get_all_subscriptions()

        # Чтобы не парсить один URL 100 раз, используем множество уникальных ссылок
        # Но нам нужны ID подписок для обновления.

        # Сгруппируем подписки по URL
        url_map = {}
        for sub in subscriptions:
            if sub.total_episodes is None:
                if sub.anime_url not in url_map:
                    url_map[sub.anime_url] = []
                url_map[sub.anime_url].append(sub.id)

        for url, sub_ids in url_map.items():
            info = await parser.get_anime_info(url, bot)

            if info and info['total_episodes']:
                logger.info(f"Found total episodes for {url}: {info['total_episodes']}")
                for sub_id in sub_ids:
                    await db.update_total_episodes(sub_id, info['total_episodes'])
    except Exception as e:
        logger.error(f"Checker episodes info error: {e}")
        await notify_admins(
            bot,
            f"Ошибка в Checker Episodes Info:\n<code>{str(e)}</code>",
            level="ERROR"
        )