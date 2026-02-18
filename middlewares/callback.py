import logging
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress

logger = logging.getLogger(__name__)


class CallbackAnswerMiddleware(BaseMiddleware):
    """
    Middleware для обработки всех колбэков (нажатий на кнопки).
    1. Ловит ошибку "Message is not modified" и игнорирует её.
    2. Гарантирует, что callback.answer() будет вызван (чтобы убрать часики загрузки).
    """

    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:

        logger.debug(f"User {event.from_user.id} clicked: {event.data}")
        try:
            result = await handler(event, data)

            with suppress(Exception):
                await event.answer()

            return result

        except TelegramBadRequest as e:
            if "message is not modified" in str(e):
                logger.debug(f"Skipped 'Message not modified' for user {event.from_user.id}")
                with suppress(Exception):
                    await event.answer()
                return

            raise e