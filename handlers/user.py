from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress

from database import requests as db
from keyboards import inline
from services import parser
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
    text = "👋 <b>Главное меню:</b>"
    kb = inline.main_menu()

    if is_edit:
        with suppress(TelegramBadRequest):
            await message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="HTML")


async def show_updates_for_vo(message: types.Message, state: FSMContext, vo: str):
    """
    Загружает и показывает список обновлений.
    """
    try:
        await message.edit_text(
            f"⏳ <b>Загружаю обновления ({vo})...</b>\n<i>Пожалуйста, подождите.</i>",
            parse_mode="HTML"
        )
    except TelegramBadRequest:
        pass  # Если сообщение уже такое, игнорируем

    updates = await parser.get_filtered(vo, message.bot)

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
        await state.update_data(current_updates=updates, current_vo=vo)
        await state.set_state(UpdatesState.viewing_list)
        await message.edit_text(
            f"😔 Свежих серий с озвучкой <b>{vo}</b> не найдено.",
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

    await state.update_data(current_updates=updates, current_vo=vo)
    await state.set_state(UpdatesState.viewing_list)

    await message.edit_text(
        result_text,
        reply_markup=inline.updates_list_actions(updates),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


# --- СТАРТ ---
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    is_new_user = await db.add_user(message.from_user.id, message.from_user.username)
    user = await db.get_user(message.from_user.id)

    if is_new_user or (user and not user.favorite_voiceover):
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Для начала работы выбери твою <b>любимую озвучку</b>.\n"
            "Я буду показывать обновления именно для неё по умолчанию.",
            reply_markup=inline.voiceover_selection("Не выбрано", mode="save"),
            parse_mode="HTML"
        )
    else:
        await render_main_menu(message, message.from_user.id, is_edit=False)


@router.callback_query(F.data == "back_home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await render_main_menu(callback.message, callback.from_user.id, is_edit=True)


# --- ПОЛУЧЕНИЕ ОБНОВЛЕНИЙ (DEFAULT) ---
@router.callback_query(F.data == "get_updates_default")
async def cb_get_updates_default(callback: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    vo = user.favorite_voiceover if user and user.favorite_voiceover else "AniLiberty"

    await callback.answer(f"🚀 Загружаю: {vo}...", cache_time=5)

    await show_updates_for_vo(callback.message, state, vo)


# --- ВЫБОР ДРУГОЙ ОЗВУЧКИ (БЕЗ СОХРАНЕНИЯ) ---
@router.callback_query(F.data == "select_other_vo")
async def cb_select_other_vo(callback: types.CallbackQuery):
    await callback.answer("🎙 Выбор режима просмотра")
    await callback.message.edit_text(
        "Выберите озвучку для просмотра списка <i>(это не изменит настройки по умолчанию)</i>:",
        reply_markup=inline.voiceover_selection("", mode="view"),
        parse_mode="HTML"
    )


# --- НАСТРОЙКИ (С СОХРАНЕНИЕМ) ---
@router.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    vo = user.favorite_voiceover if user else "Не выбрано"

    await callback.answer("⚙️ Настройки")
    await callback.message.edit_text(
        f"💾 <b>Настройки</b>\n"
        f"Текущая любимая озвучка: <b>{vo}</b>\n\n"
        "Выберите новую, чтобы бот запомнил её:",
        reply_markup=inline.voiceover_selection(vo, mode="save"),
        parse_mode="HTML"
    )


# --- ОБРАБОТКА ВЫБОРА ОЗВУЧКИ (ОБЩАЯ) ---
@router.callback_query(F.data.startswith("set_vo_"))
async def cb_handle_vo_selection(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    mode = parts[2]  # save или view
    vo = callback.data.replace(f"set_vo_{mode}_", "")

    if mode == "save":
        await db.update_user_voiceover(callback.from_user.id, vo)
        await callback.answer(f"✅ Сохранено: {vo}", show_alert=False)
        await callback.message.edit_reply_markup(reply_markup=inline.voiceover_selection(vo, mode="save"))

    elif mode == "view":
        await callback.answer(f"👁 Загружаю: {vo}")
        await show_updates_for_vo(callback.message, state, vo)


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

    # 2. Проверка ограничений
    if info.get('status') and "Вышел" in info['status']:
        await msg.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\n"
            f"<b>Причина:</b> Аниме уже полностью вышло.",
            parse_mode="HTML"
        )
        await callback.answer("⛔️ Нельзя добавить", cache_time=5)
        return

    if info.get('type') and "Фильм" in info['type']:
        await msg.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\n"
            f"<b>Причина:</b> Это фильм (обновлений не будет).",
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
    vo = data.get("current_vo", "AniLiberty")

    await callback.answer("🔄 Обновляю список...")
    await show_updates_for_vo(callback.message, state, vo)


# --- РАСПИСАНИЕ И ПОДПИСКА ---
@router.callback_query(F.data == "open_schedule")
async def cb_open_schedule(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("📅 Загружаю расписание...")

    # 1. Парсим расписание
    schedule_items = await parser.get_schedule(callback.bot)

    if schedule_items is None:
        await callback.message.edit_text(
            "⚠️ Ошибка получения расписания. Попробуйте позже.",
            reply_markup=inline.back_button()
        )
        return

    if not schedule_items:
        await callback.message.edit_text(
            "📭 Расписание пока пусто.",
            reply_markup=inline.back_button()
        )
        return

    lines = ["📅 <b>Ближайшие выходы аниме:</b>\n"]
    current_day = ""

    # Ограничение ввода, для отсутствия в упор в лимит (надо обойти для отображения всего сразу)
    limit = 20
    schedule_items = schedule_items[:limit]

    for i, item in enumerate(schedule_items):
        # Группировка по дням
        if item['day'] != current_day:
            current_day = item['day']
            lines.append(f"\n📆 <b>{current_day}</b>")

        lines.append(
            f"<b>{i + 1}.</b> <a href='{item['link']}'>{item['title']}</a> — {item['time']}"
        )

    lines.append("\n<i>Нажмите номер, чтобы выбрать озвучку и подписаться.</i>")

    await state.update_data(schedule_items=schedule_items)
    await state.set_state(ScheduleState.viewing_schedule)

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=inline.schedule_list_actions(len(schedule_items)),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("sched_sel_"), StateFilter(ScheduleState.viewing_schedule))
async def cb_schedule_item_selected(callback: types.CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[-1])
    data = await state.get_data()
    items = data.get("schedule_items", [])

    if idx >= len(items):
        await callback.answer("⚠️ Список устарел", show_alert=True)
        return

    anime = items[idx]

    await callback.answer(f"🔍 {anime['title']}...")

    info = await parser.get_anime_details(anime['link'], callback.bot)

    if not info:
        await callback.answer("❌ Не удалось получить данные об аниме", show_alert=True)
        return

    # Проверки (Статус/Тип)
    if info.get('status') and "Вышел" in info['status']:
        await callback.message.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\nПричина: Аниме завершено.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    if info.get('type') and "Фильм" in info['type']:
        await callback.message.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\nПричина: Это фильм.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    # Если озвучек нет
    voiceovers = info.get('available_voiceovers', [])
    if not voiceovers:
        await callback.message.edit_text(
            f"⚠️ Для аниме <b>{anime['title']}</b> пока нет доступных озвучек.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    await state.update_data(
        selected_anime_title=anime['title'],
        selected_anime_url=anime['link'],
        selected_anime_total=info['total_episodes']
    )

    await state.set_state(ScheduleState.selecting_voiceover)
    await callback.message.edit_text(
        f"📺 <b>{anime['title']}</b>\n"
        f"Выберите озвучку для подписки:",
        reply_markup=inline.anime_voiceovers_list(voiceovers),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("sched_sub_vo_"), StateFilter(ScheduleState.selecting_voiceover))
async def cb_schedule_sub_finalize(callback: types.CallbackQuery, state: FSMContext):
    # Получаем выбранную озвучку
    vo = callback.data.replace("sched_sub_vo_", "")

    data = await state.get_data()
    title = data.get("selected_anime_title")
    url = data.get("selected_anime_url")
    total_eps = data.get("selected_anime_total")

    # Для новой подписки last_episode = "0" (или "Серия 0") нормально, чтобы при выходе новой пришло уведомление.

    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=title,
        url=url,
        last_ep="Серия 0",  # Начальное значение
        voiceover=vo,
        total_eps=total_eps
    )

    total_str = total_eps if total_eps else "?"

    if success:
        await callback.message.edit_text(
            f"✅ <b>Подписка оформлена!</b>\n\n"
            f"📺 {title}\n"
            f"🎙 {vo}\n"
            f"📊 Эпизоды: ? / {total_str}",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("⚠️ Вы уже подписаны на это сочетание", show_alert=True)


@router.callback_query(F.data == "cancel_schedule")
async def cb_cancel_schedule(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await render_main_menu(callback.message, callback.from_user.id, is_edit=True)


# --- МОИ ПОДПИСКИ ---
@router.callback_query(F.data == "my_subs")
async def cb_my_subs(callback: types.CallbackQuery):
    await callback.answer("📋 Загружаю подписки...")
    subs = await db.get_user_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.edit_text(
            "📭 <b>У вас пока нет подписок.</b>\n"
            "Добавьте аниме через поиск или список свежих серий.",
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

    await callback.message.edit_text(
        "\n".join(text_lines),
        reply_markup=inline.subs_list_actions(subs),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@router.callback_query(F.data.startswith("unsub_"))
async def cb_unsubscribe(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("unsub_")[1])

    await db.delete_subscription(sub_id)
    await callback.answer("🗑 Подписка удалена")

    # Обновляем список (рекурсивно вызываем функцию просмотра подписок)
    await cb_my_subs(callback)