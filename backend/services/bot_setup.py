"""
Команды в меню «/» и кнопка мини-аппа слева от поля ввода. Настраиваются при каждом старте бота.
"""
import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, MenuButtonWebApp, WebAppInfo

import config

logger = logging.getLogger(__name__)

APP_MENU_BUTTON_TEXT = "Приложение"

USER_COMMANDS = [
    BotCommand(command="menu", description="Меню в чате"),
    BotCommand(command="updates", description="Свежие серии любимых озвучек"),
    BotCommand(command="schedule", description="Расписание и подписка"),
    BotCommand(command="subs", description="Мои подписки"),
    BotCommand(command="find", description="Найти тайтл на YummyAnime"),
    BotCommand(command="voiceovers", description="Любимые озвучки"),
    BotCommand(command="app", description="Открыть приложение"),
    BotCommand(command="help", description="Что умеет бот"),
]
ADMIN_COMMAND = BotCommand(command="admin", description="Панель администратора")


def user_commands() -> list[BotCommand]:
    # Без адреса мини-аппа команда /app только сообщает, что приложения нет — в подсказках она не нужна
    return [
        command for command in USER_COMMANDS
        if (config.MINIAPP_URL or command.command != "app") and (config.YUMMY_ENABLED or command.command != "find")
    ]


async def configure_bot(bot: Bot) -> None:
    commands = user_commands()
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        logger.error(f"Failed to set bot commands: {e}")

    admin_commands = [*commands, ADMIN_COMMAND]
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
        except Exception as e:
            # Например, админ ещё не запускал бота
            logger.warning(f"Failed to set admin commands for {admin_id}: {e}")

    if not config.MINIAPP_URL:
        logger.info("MINIAPP_URL is not set: chat menu button is left unchanged")
        return
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text=APP_MENU_BUTTON_TEXT, web_app=WebAppInfo(url=config.MINIAPP_URL))
        )
    except Exception as e:
        logger.error(f"Failed to set chat menu button: {e}")
