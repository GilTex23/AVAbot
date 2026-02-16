from aiogram import Router
from aiogram.types import ErrorEvent
from services.notifier import notify_admins
import logging
import traceback

router = Router()
logger = logging.getLogger(__name__)


@router.error()
async def global_error_handler(event: ErrorEvent, bot):
    """
    Ловит все необработанные ошибки в боте
    """
    exception = event.exception
    tb = traceback.format_exc()

    logger.error(f"Global error: {exception}")

    error_message = (
        f"🔥 <b>Необработанная ошибка!</b>\n"
        f"Update: {event.update.update_id}\n"
        f"Ошибка: <code>{str(exception)}</code>\n\n"
        f"Traceback:\n<pre>{tb[-1000:]}</pre>"
    )

    await notify_admins(bot, error_message, level="CRITICAL")