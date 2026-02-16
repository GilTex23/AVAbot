import logging
from aiogram import Bot
import config

logger = logging.getLogger(__name__)


async def notify_admins(bot: Bot, message: str, level: str = "INFO"):
    """
    Отправляет уведомление всем администраторам с цветовой дифференциацией по уровню.

    :param bot: Экземпляр бота
    :param message: Текст сообщения
    :param level: Уровень (INFO, WARNING, ERROR, CRITICAL)
    """

    levels = {
        "INFO": "ℹ️ <b>INFO</b>",
        "WARNING": "⚠️ <b>WARNING</b>",
        "ERROR": "❌ <b>ERROR</b>",
        "CRITICAL": "🚨 <b>CRITICAL ERROR</b>"
    }

    header = levels.get(level.upper(), levels["INFO"])

    full_text = f"{header}\n\n{message}"

    if len(full_text) > 4000:
        full_text = full_text[:4000] + "... (сообщение обрезано)"

    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=full_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")


async def send_error(bot: Bot, error: Exception, context: str = ""):
    """
    Упрощенная обертка для отправки исключений.
    """
    msg = f"Произошла ошибка: {error}"
    if context:
        msg = f"Контекст: <b>{context}</b>\n{msg}"

    await notify_admins(bot, msg, level="ERROR")