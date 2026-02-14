from aiogram import Router, types
from aiogram.filters import Command, Filter
import config
import logging
import os

router = Router()

class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in config.ADMIN_IDS

@router.message(IsAdmin(), Command("logs"))
async def cmd_logs(message: types.Message):
    """Отправка файла логов"""
    log_file = types.FSInputFile("logs/bot.log")
    try:
        await message.answer_document(log_file, caption="📄 Актуальные логи")
    except Exception as e:
        await message.answer(f"Ошибка отправки логов: {e}")