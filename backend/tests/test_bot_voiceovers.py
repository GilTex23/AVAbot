"""Сценарии бота с любимыми озвучками: запросы к Telegram подменены, база настоящая."""
import datetime as dt
import itertools

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from handlers import user as user_handlers
from services import parser, stats

USER_ID = 70
UPDATES = [
    {"title": "A", "episode": "Серия 1", "studio": "AniLiberty", "link": "https://animego.me/anime/a", "poster_url": ""},
    {"title": "B", "episode": "Серия 2", "studio": "AniDUB", "link": "https://animego.me/anime/b", "poster_url": ""},
    {"title": "C", "episode": "Серия 3", "studio": "AniLiberty", "link": "https://animego.me/anime/c", "poster_url": ""},
]


class RecordingSession(BaseSession):
    """Вместо Telegram: запоминает вызовы и отвечает правдоподобными объектами"""

    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, (SendMessage, EditMessageText)):
            # Как ответ настоящего Telegram: сообщение привязано к боту, его можно редактировать
            return Message(
                message_id=1, date=dt.datetime.now(), chat=Chat(id=USER_ID, type="private"),
                text=method.text, reply_markup=method.reply_markup,
            ).as_(bot)
        return True

    async def stream_content(self, *args, **kwargs):
        raise NotImplementedError

    async def close(self):
        pass

    def last(self, method_type):
        return next(call for call in reversed(self.calls) if isinstance(call, method_type))


@pytest.fixture
async def telegram(database, monkeypatch):
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    dp = Dispatcher(storage=MemoryStorage())
    # Роутер модуля — один на процесс, подключаем его к новому диспетчеру
    user_handlers.router._parent_router = None
    dp.include_router(user_handlers.router)
    update_ids = itertools.count(1)
    sender = User(id=USER_ID, is_bot=False, first_name="Тест")
    chat = Chat(id=USER_ID, type="private")

    async def fake_updates(bot_):
        return UPDATES

    monkeypatch.setattr(parser, "get_updates", fake_updates)
    monkeypatch.setattr(stats, "_active_marked", set())

    async def send(text):
        message = Message(message_id=1, date=dt.datetime.now(), chat=chat, from_user=sender, text=text)
        await dp.feed_update(bot, Update(update_id=next(update_ids), message=message))

    async def press(data):
        message = Message(message_id=1, date=dt.datetime.now(), chat=chat, from_user=sender, text="…")
        query = CallbackQuery(id=str(next(update_ids)), from_user=sender, chat_instance="1", message=message, data=data)
        await dp.feed_update(bot, Update(update_id=next(update_ids), callback_query=query))

    yield session, send, press
    user_handlers.router._parent_router = None


def buttons(method):
    return [button for row in method.reply_markup.inline_keyboard for button in row]


def button(method, text):
    return next(item for item in buttons(method) if item.text == text)


async def test_start_and_favorites_flow(database, telegram):
    session, send, press = telegram
    await database.touch_voiceovers(["AniLiberty", "AniDUB", "MDA"])

    await send("/start")
    welcome = session.last(SendMessage)
    assert "Привет, Тест" in welcome.text and "показываю все" in welcome.text
    assert [item.text for item in buttons(welcome)] == ["💬 Меню в чате", "🎙 Выбрать любимые озвучки"]

    await press(button(welcome, "🎙 Выбрать любимые озвучки").callback_data)
    onboarding = session.last(EditMessageText)
    assert "Любимые озвучки" in onboarding.text and buttons(onboarding)[-1].text == "✅ Готово"

    await press(button(onboarding, "AniLiberty").callback_data)
    assert await database.get_user_favorite_voiceovers(USER_ID) == ["AniLiberty"]
    marked = session.last(EditMessageText)
    assert "✅ AniLiberty" in [item.text for item in buttons(marked)] and "Сейчас: <b>AniLiberty</b>" in marked.text

    await press("back_home")
    menu = session.last(EditMessageText)
    assert "AniLiberty" in menu.text and buttons(menu)[0].text == "🔥 Свежие серии (любимые)"

    await press("get_updates_default")
    favorites_list = session.last(EditMessageText)
    assert "https://animego.me/anime/a" in favorites_list.text and "https://animego.me/anime/b" not in favorites_list.text

    await press("select_other_vo")
    studios = session.last(EditMessageText)
    assert [item.text for item in buttons(studios)][:2] == ["AniLiberty (2)", "AniDUB (1)"]
    await press(button(studios, "AniDUB (1)").callback_data)
    one = session.last(EditMessageText)
    assert "https://animego.me/anime/b" in one.text and "https://animego.me/anime/a" not in one.text

    await press("refresh_updates")
    assert "https://animego.me/anime/b" in session.last(EditMessageText).text

    await press("settings")
    settings = session.last(EditMessageText)
    await press(button(settings, "♻️ Сбросить — все озвучки").callback_data)
    assert await database.get_user_favorite_voiceovers(USER_ID) == []

    await press("set_vo_save_AniLiberty")
    outdated = session.last(AnswerCallbackQuery)
    assert outdated.show_alert and "/start" in outdated.text
