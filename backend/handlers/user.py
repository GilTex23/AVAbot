from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress
import html

from database import requests as db
from keyboards import inline
import config
from services import anime_titles, parser, shikimori_sync, stats, voiceovers
from services.subscription_rules import subscription_block_reason
from utils.states import UpdatesState, ScheduleState
import logging

router = Router()
logger = logging.getLogger(__name__)


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def render_main_menu(message: types.Message, user_id: int, is_edit: bool = False):
    """
    Универсальная функция для показа главного меню.
    is_edit=True -> редактируем старое сообщение
    is_edit=False -> отправляем новое (для команды /start)
    """
    # Текст меню
    favorites = await db.get_user_favorite_voiceovers(user_id)
    text = f"👋 <b>Главное меню:</b>\n🎙 Любимые озвучки: <i>{html.escape(voiceovers.describe(favorites))}</i>"
    kb = inline.main_menu(has_favorites=bool(favorites))

    if is_edit:
        with suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_updates_for_vo(message: types.Message, state: FSMContext, names: list[str], label: str):
    """
    Загружает и показывает свежие серии для списка озвучек (пустой список — все).
    label — как назвать выборку в тексте: «AniLiberty», «Все озвучки».
    """
    vo = html.escape(label)
    try:
        await message.edit_text(
            f"⏳ <b>Загружаю обновления ({vo})...</b>\n<i>Пожалуйста, подождите.</i>",
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass  # Если сообщение уже такое, игнорируем

    updates = await parser.get_filtered(names, message.bot)

    if updates is None:
        await message.edit_text(
            "⚠️ <b>Ошибка получения данных.</b>\n"
            "Сервис временно недоступен или произошла ошибка сети.\n"
            "Пожалуйста, повторите попытку позже.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    if not updates:
        await state.update_data(current_updates=updates, current_names=names, current_label=label)
        await state.set_state(UpdatesState.viewing_list)
        await message.edit_text(
            f"😔 Свежих серий (<b>{vo}</b>) не найдено.",
            reply_markup=inline.updates_list_actions(updates),
            parse_mode="HTML"
        )
        return

    text_lines = [f"🔥 <b>Свежие серии ({vo}):</b>\n"]
    for i, anime in enumerate(updates):
        # text_lines.append(
        #     f"<b>{i + 1}.</b> <a href='{anime['link']}'>{anime['title']}</a>\n"
        #     f"🎬 <b>{anime['episode']}</b> <i>({anime['studio']})</i>"
        # )
        text_lines.append(
            f"<b>{i + 1}.</b> <a href='{anime['link']}'>{anime['title']}</a>\n"
            f"   └ <b><i>{anime['episode']}</i></b> • <i>{anime['studio']}</i>"
        )

    text_lines.append("\n<i>Нажми на кнопку с номером, чтобы добавить аниме в любимые.</i>")
    result_text = "\n".join(text_lines)

    await state.update_data(current_updates=updates, current_names=names, current_label=label)
    await state.set_state(UpdatesState.viewing_list)

    await message.edit_text(
        result_text,
        reply_markup=inline.updates_list_actions(updates),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# --- СТАРТ И КОМАНДЫ ---
HELP_TEXT = (
    "🤖 <b>Что я умею</b>\n"
    "Слежу за новыми сериями аниме в озвучке с AnimeGO и пишу, когда на ваших подписках выходит серия.\n\n"
    "/menu — меню в чате\n"
    "/updates — свежие серии любимых озвучек\n"
    "/schedule — расписание, отсюда можно подписаться\n"
    "/subs — мои подписки\n"
    "/voiceovers — любимые озвучки\n"
    "/app — открыть приложение\n"
    "/help — эта справка\n\n"
    "Ссылкой на тайтл можно поделиться: тот, кто её откроет, сразу увидит выбор озвучки для подписки."
)


def welcome_text(first_name: str | None) -> str:
    lines = [
        f"👋 Привет, {html.escape(first_name or '')}!",
        "",
        "Я слежу за новыми сериями аниме в озвучке с AnimeGO и пишу, когда на ваших подписках выходит серия.",
        "",
    ]
    if config.MINIAPP_URL:
        lines.append("Удобнее всего — в приложении: свежие серии, расписание, подписки и прогноз выхода. "
                     "Всё то же можно делать и здесь, в чате.")
    else:
        lines.append("Свежие серии, расписание и подписки — в меню ниже.")
    lines += ["", "<i>Любимые озвучки можно выбрать сейчас или позже — пока показываю все.</i>"]
    return "\n".join(lines)


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject):
    await state.clear()

    is_new_user = await db.add_user(message.from_user.id, message.from_user.username)

    # Ссылка на тайтл: t.me/бот?start=a3484
    anime_id = anime_titles.parse_payload(command.args)
    if anime_id is not None:
        if is_new_user:
            await message.answer(welcome_text(message.from_user.first_name), reply_markup=inline.welcome(), parse_mode="HTML")
        await open_title(message, state, anime_id)
        return

    if is_new_user:
        await message.answer(welcome_text(message.from_user.first_name), reply_markup=inline.welcome(), parse_mode="HTML")
    else:
        await render_main_menu(message, message.from_user.id, is_edit=False)


@router.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await db.add_user(message.from_user.id, message.from_user.username)
    await render_main_menu(message, message.from_user.id, is_edit=False)


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(HELP_TEXT, reply_markup=inline.open_app(), parse_mode="HTML")


@router.message(Command("app"))
async def cmd_app(message: types.Message):
    if not config.MINIAPP_URL:
        await message.answer("📱 Приложение пока не подключено. Всё доступно в меню: /menu")
        return
    await message.answer("📱 Свежие серии, расписание, подписки и прогноз выхода серий:", reply_markup=inline.open_app())


@router.message(Command("updates"))
async def cmd_updates(message: types.Message, state: FSMContext):
    await db.add_user(message.from_user.id, message.from_user.username)
    favorites = await db.get_user_favorite_voiceovers(message.from_user.id)
    msg = await message.answer("⏳ <b>Загружаю обновления...</b>", parse_mode="HTML")
    await show_updates_for_vo(msg, state, favorites, voiceovers.describe(favorites))


@router.message(Command("schedule"))
async def cmd_schedule(message: types.Message, state: FSMContext):
    await db.add_user(message.from_user.id, message.from_user.username)
    msg = await message.answer("⏳ <b>Загружаю расписание аниме...</b>", parse_mode="HTML")
    await load_schedule(msg, message.from_user.id, state)


@router.message(Command("subs"))
async def cmd_subs(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await render_subscriptions(message, message.from_user.id, is_edit=False)


@router.message(Command("voiceovers"))
async def cmd_voiceovers(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    text, kb = await favorites_screen(message.from_user.id, page=0, context=inline.FAVORITES_SETTINGS)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def open_title(message: types.Message, state: FSMContext, anime_id: int):
    """Тайтл по ссылке: название из anime_titles, дальше — выбор озвучки, как из расписания"""
    title = await db.get_anime_title(anime_id)
    if title is None:
        await message.answer(
            "🔍 Не нашёл этот тайтл: он ещё не появлялся в ленте или расписании. Попробуйте найти его в /schedule.",
            reply_markup=inline.back_button(),
        )
        return
    msg = await message.answer(f"📺 <b>{html.escape(title.title)}</b>\n🔍 Загружаю озвучки...", parse_mode="HTML")
    await offer_voiceovers(msg, state, title.title, title.url, message.bot)


@router.callback_query(F.data == "back_home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await render_main_menu(callback.message, callback.from_user.id, is_edit=True)


# --- ПОЛУЧЕНИЕ ОБНОВЛЕНИЙ ПО ЛЮБИМЫМ ОЗВУЧКАМ ---
@router.callback_query(F.data == "get_updates_default")
async def cb_get_updates_default(callback: types.CallbackQuery, state: FSMContext):
    favorites = await db.get_user_favorite_voiceovers(callback.from_user.id)
    label = voiceovers.describe(favorites)

    await callback.answer(f"🚀 Загружаю: {label}...", cache_time=5)

    await show_updates_for_vo(callback.message, state, favorites, label)


# --- ДРУГАЯ ОЗВУЧКА: ТЕ, ЧТО СЕЙЧАС ЕСТЬ В ЛЕНТЕ (БЕЗ СОХРАНЕНИЯ) ---
@router.callback_query(F.data == "select_other_vo")
async def cb_select_other_vo(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("🎙 Выбор озвучки")
    with suppress(TelegramBadRequest):
        await callback.message.edit_text("⏳ <b>Смотрю, какие озвучки есть в ленте...</b>", parse_mode="HTML")

    updates = await parser.get_updates(callback.bot)
    if updates is None:
        await callback.message.edit_text(
            "⚠️ <b>Ошибка получения данных.</b>\nПожалуйста, повторите попытку позже.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    studios = voiceovers.studios_in(updates)
    await state.update_data(feed_studios=[studio["name"] for studio in studios])
    await callback.message.edit_text(
        "Выберите озвучку из свежих серий <i>(любимые озвучки не изменятся)</i>.\n"
        "<i>В скобках — сколько серий сейчас в ленте.</i>",
        reply_markup=inline.feed_voiceovers(studios),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("vo_view:"))
async def cb_view_voiceover(callback: types.CallbackQuery, state: FSMContext):
    choice = callback.data.split(":", 1)[1]
    if choice == "all":
        label = voiceovers.describe([])
        await callback.answer(f"👁 Загружаю: {label}")
        await show_updates_for_vo(callback.message, state, [], label)
        return

    studios = (await state.get_data()).get("feed_studios") or []
    if not choice.isdigit() or int(choice) >= len(studios):
        await callback.answer("⚠️ Список устарел, откройте его заново.", show_alert=True)
        return

    name = studios[int(choice)]
    await callback.answer(f"👁 Загружаю: {name}")
    await show_updates_for_vo(callback.message, state, [name], name)


# --- ЛЮБИМЫЕ ОЗВУЧКИ (С СОХРАНЕНИЕМ) ---
async def favorites_screen(user_id: int, page: int, context: str):
    catalog = await voiceovers.catalog()
    favorites = await db.get_user_favorite_voiceovers(user_id)

    lines = [
        "🎙 <b>Любимые озвучки</b>",
        f"Сейчас: <b>{html.escape(voiceovers.describe(favorites, limit=10))}</b>",
        "",
        "Отметьте озвучки — «Свежие серии» будут показывать только их. Ничего не отмечено — показываются все.",
    ]
    if catalog:
        lines.append(f"<i>Сверху — самые активные за {voiceovers.POPULAR_DAYS} дней.</i>")
    else:
        lines.append("<i>Список озвучек появится после первой проверки ленты.</i>")
    return "\n".join(lines), inline.favorite_voiceovers(catalog, favorites, page, context)


async def render_favorites(message: types.Message, user_id: int, page: int, context: str):
    text, kb = await favorites_screen(user_id, page, context)
    with suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    await callback.answer("⚙️ Любимые озвучки")
    await render_favorites(callback.message, callback.from_user.id, page=0, context=inline.FAVORITES_SETTINGS)


@router.callback_query(F.data.startswith("fav:"))
async def cb_favorites(callback: types.CallbackQuery):
    # fav:t:<id>:<page>:<ctx> — отметить или снять, fav:p:<page>:<ctx> — страница, fav:c:<page>:<ctx> — сбросить
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer()
        return
    action, context = parts[1], parts[-1]
    page = int(parts[-2]) if parts[-2].isdigit() else 0
    user_id = callback.from_user.id

    if action == "t" and parts[2].isdigit():
        catalog = await voiceovers.catalog()
        item = next((item for item in catalog if item["id"] == int(parts[2])), None)
        if item is None:
            await callback.answer("⚠️ Такой озвучки больше нет в списке.", show_alert=True)
        else:
            favorites = await db.get_user_favorite_voiceovers(user_id)
            if item["name"] in favorites:
                favorites.remove(item["name"])
                await callback.answer(f"Убрано: {item['name']}")
            elif len(favorites) >= voiceovers.MAX_FAVORITES:
                await callback.answer(f"⚠️ Можно выбрать не больше {voiceovers.MAX_FAVORITES} озвучек.", show_alert=True)
                return
            else:
                favorites.append(item["name"])
                await callback.answer(f"✅ Добавлено: {item['name']}")
            await db.update_user_favorite_voiceovers(user_id, favorites)
    elif action == "c":
        await db.update_user_favorite_voiceovers(user_id, [])
        await callback.answer("♻️ Показываю все озвучки")

    await render_favorites(callback.message, user_id, page, context)


# --- ДОБАВЛЕНИЕ В ИЗБРАННОЕ ИЗ СПИСКА (FSM) ---
@router.callback_query(F.data.startswith("add_from_list_"), StateFilter(UpdatesState.viewing_list))
async def cb_add_from_list(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[-1])
    data = await state.get_data()
    updates = data.get("current_updates", [])

    if not updates or idx >= len(updates):
        await callback.answer("⚠️ Список устарел, обновите его.", show_alert=True)
        return

    anime = updates[idx]

    await callback.answer("🔍 Проверяю статус аниме...", cache_time=2)
    msg = await callback.message.answer("🔍 Проверяю статус аниме...")


    info = await parser.get_anime_info(anime['link'], callback.bot)

    if not info:
        await msg.edit_text("⚠️ Не удалось получить информацию об аниме. Попробуйте позже.")
        await callback.answer("⚠️ Не удалось получить информацию об аниме. Попробуйте позже.", cache_time=10)
        return

    # 2. Проверка ограничений (то же правило, что в мини-аппе)
    reason = subscription_block_reason(info, anime['episode'])
    if reason:
        await msg.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\n"
            f"<b>Причина:</b> {reason}",
            parse_mode="HTML"
        )
        await callback.answer("⛔️ Нельзя добавить", cache_time=5)
        return

    # 3. Добавляем в БД
    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=anime['title'],
        url=anime['link'],
        last_ep=anime['episode'],
        voiceover=anime['studio'],
        total_eps=info['total_episodes']
    )
    if success:
        await stats.increment("subscriptions.created", stats.SOURCE_BOT)
        await anime_titles.remember([anime])
        shikimori_sync.kick(anime['link'])

    if success:
        total_str = info['total_episodes'] if info['total_episodes'] else "?"
        # Показываем успех и кнопку возврата к списку
        await msg.edit_text(
            f"✅ <b>Успешно добавлено!</b>\n\n"
            f"📺 <b>{anime['title']}</b>\n"
            f"🎙 Озвучка: {anime['studio']}\n"
            f"📊 Прогресс: {anime['episode']} / {total_str}",
            parse_mode="HTML"
        )
    else:
        await msg.edit_text(f"⚠️ Вы уже подписаны на аниме <b>{anime['title']}</b> с озвучкой \"{anime['studio']}\".",
                            parse_mode="HTML")
        await callback.answer(f"⚠️ {anime['title']} уже в ваших подписках!", cache_time=10)


@router.callback_query(F.data == "refresh_updates", StateFilter(UpdatesState.viewing_list))
async def cb_refresh(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    names = data.get("current_names") or []

    await callback.answer("🔄 Обновляю список...")
    await show_updates_for_vo(callback.message, state, names, data.get("current_label") or voiceovers.describe(names))


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ОТРИСОВКИ ДНЯ ---
async def render_schedule_day(message: types.Message, state: FSMContext):
    data = await state.get_data()
    schedule = data.get("schedule_days", [])
    current_idx = data.get("current_day_index", 0)

    if not schedule:
        await message.edit_text("📭 Расписание пусто.", reply_markup=inline.back_button())
        return

    day_data = schedule[current_idx]
    date_str = day_data['date_str']
    items = day_data['items']

    lines = [f"📅 <b>Расписание: {date_str}</b>\n"]
    for i, item in enumerate(items):
        lines.append(
            f"<b>{i + 1}.</b> <a href='{item['link']}'>{item['title']}</a> — {item['time']}"
        )

    lines.append("\n<i>Выберите номер аниме для добавления:</i>")

    kb = inline.schedule_day_view(current_idx, len(schedule), len(items))

    with suppress(TelegramBadRequest):
        await message.edit_text("\n".join(lines), reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)


# --- ОТКРЫТИЕ РАСПИСАНИЯ ---
@router.callback_query(F.data == "open_schedule")
async def cb_open_schedule(callback: types.CallbackQuery, state: FSMContext):
    try:
        await callback.message.edit_text(
            "⏳ <b>Загружаю расписание аниме...</b>\n<i>Пожалуйста, подождите.</i>",
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass

    await load_schedule(callback.message, callback.from_user.id, state)


async def load_schedule(message: types.Message, user_id: int, state: FSMContext):
    """Загружает расписание и показывает первый день в сообщении message (оно редактируется)"""
    schedule_days = await parser.get_schedule(message.bot)

    if schedule_days is None:
        await message.edit_text(
            "⚠️ Ошибка получения расписания. Попробуйте позже.",
            reply_markup=inline.back_button()
        )
        return

    # Время и дни — в часовом поясе из настроек мини-аппа (по умолчанию Москва)
    user = await db.get_user(user_id)
    schedule_days = parser.localize_schedule(schedule_days, parser.zone_or_moscow(user.quiet_timezone if user else None))

    await state.update_data(schedule_days=schedule_days, current_day_index=0)
    await state.set_state(ScheduleState.viewing_schedule)

    await render_schedule_day(message, state)


# --- НАВИГАЦИЯ ПО ДНЯМ ---
@router.callback_query(F.data.startswith("sched_day_"), StateFilter(ScheduleState.viewing_schedule))
async def cb_schedule_nav(callback: types.CallbackQuery, state: FSMContext):
    new_index = int(callback.data.split("_")[-1])

    await state.update_data(current_day_index=new_index)
    await callback.answer()  # Убираем часики
    await render_schedule_day(callback.message, state)


# --- ВЫБОР АНИМЕ (ОТПРАВКА НОВОГО СООБЩЕНИЯ) ---
@router.callback_query(F.data.startswith("sched_item_"), StateFilter(ScheduleState.viewing_schedule))
async def cb_schedule_item_select(callback: types.CallbackQuery, state: FSMContext):
    item_idx = int(callback.data.split("_")[-1])

    data = await state.get_data()
    schedule = data.get("schedule_days", [])
    day_idx = data.get("current_day_index", 0)

    if not schedule:
        await callback.answer("⚠️ Данные устарели", show_alert=True)
        return

    anime = schedule[day_idx]['items'][item_idx]

    await callback.answer(f"🔍 {anime['title']}...", cache_time=2)
    msg = await callback.message.answer("🔍 Проверяю статус аниме...")
    await offer_voiceovers(msg, state, anime['title'], anime['link'], callback.bot)


async def offer_voiceovers(msg: types.Message, state: FSMContext, title: str, url: str, bot):
    """Страница тайтла -> проверка правила подписки -> кнопки озвучек в msg (из расписания и по ссылке)"""
    safe_title = html.escape(title)
    info = await parser.get_anime_details(url, bot)

    if not info:
        await msg.edit_text("❌ Не удалось получить данные о тайтле. Попробуйте позже.")
        return

    # Проверки (то же правило, что в мини-аппе; серия озвучки ещё не выбрана — считаем с серии 0)
    reason = subscription_block_reason(info, "Серия 0")
    if reason:
        await msg.edit_text(
            f"⛔️ Нельзя добавить <b>{safe_title}</b>.\nПричина: {reason}",
            parse_mode="HTML"
        )
        return

    anime_voiceovers = info.get('available_voiceovers', [])
    if not anime_voiceovers:
        await msg.edit_text(f"⚠️ Нет озвучек для <b>{safe_title}</b>.", parse_mode="HTML")
        return

    await state.update_data(
        selected_anime_title=title,
        selected_anime_url=url,
        selected_anime_total=info['total_episodes'],
        selected_anime_voiceovers=anime_voiceovers,
    )

    total = info['total_episodes'] or "?"
    await msg.edit_text(
        f"📺 <b>{safe_title}</b>\n"
        f"📊 Серий: {total}\n"
        f"👇 Выберите озвучку для подписки:",
        reply_markup=inline.anime_voiceovers_list(anime_voiceovers, url),
        parse_mode="HTML"
    )


# --- ФИНАЛИЗАЦИЯ ПОДПИСКИ ---
@router.callback_query(F.data.startswith("sched_sub_vo:"))
async def cb_schedule_sub_finalize(callback: types.CallbackQuery, state: FSMContext):
    index = callback.data.split(":", 1)[1]

    data = await state.get_data()
    title = data.get("selected_anime_title")
    url = data.get("selected_anime_url")
    total_eps = data.get("selected_anime_total")
    anime_voiceovers = data.get("selected_anime_voiceovers") or []
    vo = anime_voiceovers[int(index)] if index.isdigit() and int(index) < len(anime_voiceovers) else None

    if not title or not url or vo is None:
        await callback.answer("⚠️ Ошибка контекста. Повторите выбор аниме.", show_alert=True)
        await callback.message.delete()
        return

    # Уже вышедшие в озвучке серии не присылаем: подписка начинается с последней серии из истории ленты
    releases = await db.get_episode_releases({url})
    last_known = max((release.episode for release in releases if voiceovers.matches(vo, release.studio)), default=None)
    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=title,
        url=url,
        last_ep=f"Серия {last_known or 0}",
        voiceover=vo,
        total_eps=total_eps
    )

    total_str = total_eps if total_eps else "?"

    if success:
        await stats.increment("subscriptions.created", stats.SOURCE_BOT)
        await anime_titles.remember([{"title": title, "link": url}])
        shikimori_sync.kick(url)
        await callback.message.edit_text(
            f"✅ <b>Подписка оформлена!</b>\n\n"
            f"📺 {html.escape(title)}\n"
            f"🎙 {html.escape(vo)}\n"
            f"📊 Эпизоды: {last_known or '?'} / {total_str}",
            parse_mode="HTML"
        )
    else:
        await callback.answer("⚠️ Вы уже подписаны на это сочетание", show_alert=True)


# --- ЗАКРЫТИЕ ВСПОМОГАТЕЛЬНОГО СООБЩЕНИЯ ---
@router.callback_query(F.data == "close_message")
async def cb_close_message(callback: types.CallbackQuery):
    await callback.message.delete()


# --- МОИ ПОДПИСКИ ---
@router.callback_query(F.data == "my_subs")
async def cb_my_subs(callback: types.CallbackQuery):
    await callback.answer("📋 Загружаю подписки...")
    await render_subscriptions(callback.message, callback.from_user.id, is_edit=True)


async def render_subscriptions(message: types.Message, user_id: int, is_edit: bool):
    subs = await db.get_user_subscriptions(user_id)
    send = message.edit_text if is_edit else message.answer

    if not subs:
        await send(
            "📭 <b>У вас пока нет подписок.</b>\n"
            "Добавьте аниме через расписание или список свежих серий.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    # Формируем нумерованный список
    text_lines = ["📋 <b>Ваши активные подписки:</b>\n"]
    for i, sub in enumerate(subs):
        total_str = sub.total_episodes if sub.total_episodes else "?"
        last_ep_num = sub.last_episode.replace("Серия", "").strip()

        text_lines.append(
            f"<b>{i + 1}.</b> <a href='{sub.anime_url}'>{sub.anime_title}</a>\n"
            f"   └ <i>{sub.voiceover}</i> • [{last_ep_num} / {total_str}]"
        )

    text_lines.append("\n<i>Нажмите на кнопку с номером, чтобы удалить подписку.</i>")

    await send(
        "\n".join(text_lines),
        reply_markup=inline.subs_list_actions(subs),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("unsub_"))
async def cb_unsubscribe(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("unsub_")[1])
    if not any(sub.id == sub_id for sub in await db.get_user_subscriptions(callback.from_user.id)):
        await callback.answer("⚠️ Подписка не найдена", show_alert=True)
        return

    await db.delete_subscription(sub_id)
    await stats.increment("subscriptions.deleted", stats.SOURCE_BOT)
    await callback.answer("🗑 Подписка удалена")

    # Обновляем список (рекурсивно вызываем функцию просмотра подписок)
    await cb_my_subs(callback)


@router.callback_query(F.data == "ignore")
async def cb_ignore(callback: types.CallbackQuery):
    await callback.answer()


# Кнопки из сообщений, отправленных до перехода на список любимых озвучек
@router.callback_query(F.data.startswith(("set_vo_", "sched_sub_vo_")))
async def cb_outdated_voiceover_buttons(callback: types.CallbackQuery):
    await callback.answer("Меню обновилось — откройте его заново командой /start.", show_alert=True)
