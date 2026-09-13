"""Приветствие, команды, ссылки на тайтлы и настройка меню бота."""
import datetime as dt

import httpx
from aiogram import Bot
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SetChatMenuButton, SetMyCommands
from fastapi import FastAPI
from sqlalchemy import select

import config
from api.miniapp import router as miniapp_router
from database.models import Subscription
from services import anime_titles, bot_setup, forecast, parser
from test_bot_voiceovers import USER_ID, RecordingSession, button, buttons, telegram  # noqa: F401 — фикстура telegram
from test_db_flows import add_sub, init_data

TITLE_URL = "https://animego.me/anime/ochen-dlinnoe-nazvanie-taitla-kotoroe-ne-vlezet-v-payload-start-3484"
DETAILS = {"type": "ТВ Сериал", "status": "Онгоинг", "total_episodes": 12, "available_voiceovers": ["AniDUB", "AniLiberty"]}


def test_deep_link_payload():
    assert anime_titles.anime_id(TITLE_URL) == 3484
    assert anime_titles.anime_id(TITLE_URL + "/#comments") == 3484
    assert anime_titles.anime_id("https://animego.me/anime/bez-id") is None
    assert anime_titles.deep_link_payload(TITLE_URL) == "a3484"
    assert anime_titles.parse_payload("a3484") == 3484
    for payload in (None, "", "3484", "a", "b3484", "a34x", "a1234567890"):
        assert anime_titles.parse_payload(payload) is None


async def test_titles_are_remembered_from_feed_and_schedule(database):
    home = {
        "updates": [{"title": "Из ленты", "link": TITLE_URL, "poster_url": "https://img/1.jpg", "episode": "Серия 1", "studio": "AniDUB"}],
        "schedule": [{"date_str": "Сегодня", "items": [
            {"title": "Из расписания", "link": "https://animego.me/anime/drugoi-77", "poster_url": ""},
            {"title": "Без id", "link": "https://animego.me/anime/bez-id", "poster_url": ""},
        ]}],
    }
    await forecast.record_home(home, [])
    await anime_titles.remember([{"title": "Новое название", "link": TITLE_URL, "poster_url": None}])

    renamed = await database.get_anime_title(3484)
    assert renamed.title == "Новое название" and renamed.url == TITLE_URL and renamed.poster_url == "https://img/1.jpg"
    assert (await database.get_anime_title(77)).title == "Из расписания"


async def test_deep_link_subscribes_from_last_released_episode(database, telegram, monkeypatch):
    session, send, press = telegram
    await anime_titles.remember([{"title": "Длинный тайтл", "link": TITLE_URL}])
    now = dt.datetime.utcnow()
    await database.record_episode_releases([
        {"anime_url": TITLE_URL, "anime_title": "Длинный тайтл", "studio": studio, "episode": episode, "released_at": now}
        for studio, episode in (("AniLiberty", 4), ("AniLiberty", 5), ("AniDUB", 7))
    ])

    async def fake_details(url, bot):
        assert url == TITLE_URL
        return DETAILS

    monkeypatch.setattr(parser, "get_anime_details", fake_details)

    await send("/start a3484")
    sent = [call for call in session.calls if isinstance(call, SendMessage)]
    assert "Привет" in sent[0].text  # новый пользователь сначала видит приветствие
    card = session.last(EditMessageText)
    assert "Длинный тайтл" in card.text and "Серий: 12" in card.text
    assert [item.text for item in buttons(card)] == ["AniDUB", "AniLiberty", "🔗 Открыть на AnimeGO", "❌ Отмена"]
    assert button(card, "🔗 Открыть на AnimeGO").url == TITLE_URL

    await press(button(card, "AniLiberty").callback_data)
    assert "Подписка оформлена" in session.last(EditMessageText).text
    async with database.async_session() as db_session:
        sub = (await db_session.execute(select(Subscription))).scalar_one()
    # Серии 4 и 5 уже вышли — уведомление придёт только о шестой
    assert (sub.user_id, sub.voiceover, sub.last_episode, sub.total_episodes) == (USER_ID, "AniLiberty", "Серия 5", 12)

    await send("/start a999999")
    assert "Не нашёл этот тайтл" in session.last(SendMessage).text


async def test_commands(database, telegram, monkeypatch):
    session, send, press = telegram
    await database.touch_voiceovers(["AniLiberty"])

    async def fake_schedule(bot):
        return [{"date_str": "Сегодня", "items": [{"title": "Тайтл", "link": TITLE_URL, "time": "12:00", "poster_url": ""}]}]

    monkeypatch.setattr(parser, "get_schedule", fake_schedule)

    await send("/help")
    assert "/schedule" in session.last(SendMessage).text

    await send("/app")
    assert "не подключено" in session.last(SendMessage).text

    await send("/updates")
    assert "Свежие серии" in session.last(EditMessageText).text

    await send("/schedule")
    assert "Расписание: Сегодня" in session.last(EditMessageText).text

    await send("/subs")
    assert "пока нет подписок" in session.last(SendMessage).text

    await send("/voiceovers")
    assert "Любимые озвучки" in session.last(SendMessage).text

    monkeypatch.setattr(config, "MINIAPP_URL", "https://miniapp.example.com")
    await send("/menu")
    menu = session.last(SendMessage)
    assert buttons(menu)[0].web_app.url == "https://miniapp.example.com"


async def test_cannot_delete_foreign_subscription(database, telegram):
    session, send, press = telegram
    await send("/start")
    foreign = await add_sub(database, USER_ID + 1, "Чужой", TITLE_URL, "AniDUB", "Серия 1")

    await press(f"unsub_{foreign}")
    assert session.last(AnswerCallbackQuery).text == "⚠️ Подписка не найдена"
    assert len(await database.get_user_subscriptions(USER_ID + 1)) == 1


async def test_configure_bot(monkeypatch):
    session = RecordingSession()
    bot = Bot(token="42:TEST", session=session)
    monkeypatch.setattr(config, "ADMIN_IDS", [111])

    monkeypatch.setattr(config, "MINIAPP_URL", "")
    await bot_setup.configure_bot(bot)
    default, admin = [call for call in session.calls if isinstance(call, SetMyCommands)]
    assert "app" not in [command.command for command in default.commands]
    assert [command.command for command in admin.commands][-1] == "admin" and admin.scope.chat_id == 111
    assert not any(isinstance(call, SetChatMenuButton) for call in session.calls)

    session.calls.clear()
    monkeypatch.setattr(config, "MINIAPP_URL", "https://miniapp.example.com")
    await bot_setup.configure_bot(bot)
    assert "app" in [command.command for command in session.last(SetMyCommands).commands]
    assert session.last(SetChatMenuButton).menu_button.web_app.url == "https://miniapp.example.com"


async def test_miniapp_schedule_subscription_starts_from_last_release(database, monkeypatch):
    await database.record_episode_releases([
        {"anime_url": TITLE_URL, "anime_title": "Тайтл", "studio": "AniLiberty", "episode": 6, "released_at": dt.datetime.utcnow()},
    ])

    async def fake_info(url, bot):
        return {"type": "Сериал", "status": "Онгоинг", "total_episodes": 12}

    monkeypatch.setattr(parser, "get_anime_info", fake_info)
    app = FastAPI()
    app.include_router(miniapp_router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/miniapp/subscriptions", headers=init_data(80), json={
            "title": "Тайтл", "link": TITLE_URL, "episode": "Серия 0", "voiceover": "AniLiberty",
        })
    assert response.json()["created"] is True
    assert (await database.get_user_subscriptions(80))[0].last_episode == "Серия 6"
