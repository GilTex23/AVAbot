from aiogram import Bot
from services.parser import get_updates
from services.notifier import notify_admins
from database import requests as db
from database.models import User
import logging
from utils.antispam import AntiSpamNotify

logger = logging.getLogger(__name__)
antispam = AntiSpamNotify(logger)


async def check_updates(bot: Bot):
    try:
        logger.debug("Starting anime check cycle...")

        # 1. Получаем свежие данные с сайта
        updates = await get_updates()
        if not updates:
            logger.warning("Updates wasn't handled")
            return

        # 2. Получаем все подписки из БД
        subscriptions = await db.get_all_subscriptions()
        if not subscriptions:
            logger.info("Subscriptions empty")
            return

        logger.info(f"Subscriptions handled: {len(subscriptions)}")

        # 3. Сопоставляем
        for sub in subscriptions:
            # Для каждой подписки ищем совпадение в обновлениях
            for update in updates:
                # Сравниваем URL или Название (URL надежнее)
                if sub.anime_url == update['link']:

                    # Получаем пользователя (lazy load) для проверки любимой озвучки
                    # В SQLAlchemy async это требует предварительной подгрузки в запросе (см. db.get_all_subscriptions)
                    user_vo = sub.user.favorite_voiceover

                    # Проверяем условия:
                    # 1. Озвучка совпадает с любимой озвучкой пользователя
                    # 2. Эта серия еще не была отправлена (или она новее)

                    is_new_episode = sub.last_episode != update['episode']
                    is_target_vo = (user_vo.lower() in update['studio'].lower()) or (user_vo == "Все")

                    if is_new_episode and is_target_vo:
                        try:
                            await bot.send_message(
                                chat_id=sub.user_id,
                                text=(
                                    f"🔥 <b>Новая серия!</b>\n\n"
                                    f"📺 <b>{update['title']}</b>\n"
                                    f"🎬 {update['episode']}\n"
                                    f"🎙 Озвучка: {update['studio']}\n\n"
                                    f"🔗 <a href='{update['link']}'>Смотреть</a>"
                                ),
                                parse_mode="HTML"
                            )
                            logger.info(f"Notification sent to {sub.user_id} for {update['title']}")

                            # Обновляем запись в БД
                            await db.update_sub_last_episode(sub.id, update['episode'])

                        except Exception as e:
                            logger.error(f"Failed to send message to {sub.user_id}: {e}")
    except Exception as e:
        antispam.failed_requests += 1
        logger.error(f"Checker error: {e}")
        if not antispam.is_notified():
            await notify_admins(
                bot,
                f"Failed requests: {antispam.failed_requests}\nОшибка в модуле проверки обновлений (Checker):\n<code>{str(e)}</code>",
                level="ERROR"
            )
            antispam.set_notify_timestamp()
