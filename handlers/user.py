from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext

from database import requests as db
from keyboards import inline
from services import parser
from utils.states import SearchState, UpdatesState
import logging

router = Router()

logger = logging.getLogger(__name__)


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ВЫВОДА СПИСКА ---
async def show_updates_for_vo(message: types.Message, state: FSMContext, vo: str):
    """Парсит, формирует текст и кнопки для добавления"""
    msg = await message.answer(f"⏳ Загружаю обновления ({vo})...")

    # 1. Получаем список словарей
    updates = await parser.get_filtered(vo)

    if not updates:
        await msg.edit_text(
            f"😔 Свежих серий с озвучкой <b>{vo}</b> не найдено.",
            reply_markup=inline.back_button(),
            parse_mode="HTML"
        )
        return

    # 2. Формируем красивый текст
    text_lines = [f"🔥 <b>Свежие серии ({vo}):</b>\n"]
    for i, anime in enumerate(updates):
        # Нумерация для удобства
        text_lines.append(
            f"{i + 1}. <a href='{anime['link']}'>{anime['title']}</a> — {anime['episode']}"
        )

    text_lines.append("\n<i>Нажми на кнопку ниже, чтобы добавить аниме в любимые с этой озвучкой.</i>")
    result_text = "\n".join(text_lines)

    # 3. Сохраняем список и текущую озвучку в FSM, чтобы при клике на кнопку знать, что добавлять
    await state.update_data(current_updates=updates, current_vo=vo)
    await state.set_state(UpdatesState.viewing_list)

    await msg.edit_text(
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
            f"Привет! Выбери <b>любимую озвучку</b> по умолчанию.",
            reply_markup=inline.voiceover_selection("Не выбрано", mode="save"),
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "Главное меню:",
            reply_markup=inline.main_menu()
        )


@router.callback_query(F.data == "back_home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=inline.main_menu())


# --- ПОЛУЧЕНИЕ ОБНОВЛЕНИЙ (DEFAULT) ---
@router.callback_query(F.data == "get_updates_default")
async def cb_get_updates_default(callback: types.CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    vo = user.favorite_voiceover if user and user.favorite_voiceover else "AniLiberty"

    await callback.message.delete()
    await show_updates_for_vo(callback.message, state, vo)


# --- ВЫБОР ДРУГОЙ ОЗВУЧКИ (БЕЗ СОХРАНЕНИЯ) ---
@router.callback_query(F.data == "select_other_vo")
async def cb_select_other_vo(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Выберите озвучку для просмотра списка (это не изменит настройки по умолчанию):",
        reply_markup=inline.voiceover_selection("", mode="view")
    )


# --- НАСТРОЙКИ (С СОХРАНЕНИЕМ) ---
@router.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    user = await db.get_user(callback.from_user.id)
    vo = user.favorite_voiceover if user else "Не выбрано"

    await callback.message.edit_text(
        f"Текущая любимая озвучка: <b>{vo}</b>\n"
        "Выберите новую для сохранения по умолчанию:",
        reply_markup=inline.voiceover_selection(vo, mode="save"),
        parse_mode="HTML"
    )


# --- ОБРАБОТКА ВЫБОРА ОЗВУЧКИ (ОБЩАЯ) ---
@router.callback_query(F.data.startswith("set_vo_"))
async def cb_handle_vo_selection(callback: types.CallbackQuery, state: FSMContext):
    # data format: set_vo_{mode}_{vo}
    parts = callback.data.split("_")
    mode = parts[2]  # save или view
    vo = parts[3]  # Название озвучки (может содержать пробелы, аккуратнее)

    # Если в названии озвучки есть пробелы (Dream Cast), split сработает некорректно.
    # Лучше восстановить строку:
    vo = callback.data.replace(f"set_vo_{mode}_", "")

    if mode == "save":
        await db.update_user_voiceover(callback.from_user.id, vo)
        await callback.answer(f"✅ Настройки обновлены: {vo}")
        # После сохранения показываем меню
        await callback.message.edit_text("Главное меню:", reply_markup=inline.main_menu())

    elif mode == "view":
        await callback.answer(f"Загружаю {vo}...")
        await callback.message.delete()
        await show_updates_for_vo(callback.message, state, vo)


# --- ДОБАВЛЕНИЕ В ИЗБРАННОЕ ИЗ СПИСКА (FSM) ---
@router.callback_query(F.data.startswith("add_from_list_"), StateFilter(UpdatesState.viewing_list))
async def cb_add_from_list(callback: types.CallbackQuery, state: FSMContext):
    # Получаем индекс нажатой кнопки
    idx = int(callback.data.split("_")[-1])

    # Получаем сохраненные данные из состояния
    data = await state.get_data()
    updates = data.get("current_updates", [])
    current_vo = data.get("current_vo", "Unknown")

    if not updates or idx >= len(updates):
        await callback.answer("⚠️ Данные устарели. Обновите список.", show_alert=True)
        return

    anime = updates[idx]

    # Добавляем в БД
    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=anime['title'],
        url=anime['link'],
        last_ep=anime['episode'],
        voiceover=current_vo  # Важно! Добавляем с той озвучкой, список которой смотрели
    )

    if success:
        await callback.answer(f"✅ Добавлено: {anime['title']} ({current_vo})", show_alert=False)
    else:
        await callback.answer("⚠️ Вы уже подписаны на это аниме с этой озвучкой", show_alert=True)


@router.callback_query(F.data == "refresh_updates", StateFilter(UpdatesState.viewing_list))
async def cb_refresh(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    vo = data.get("current_vo", "AniLiberty")
    await callback.answer("Обновляю...")
    await show_updates_for_vo(callback.message, state, vo)


# --- ПОИСК АНИМЕ (FSM) ---
@router.callback_query(F.data == "search_anime")
async def cb_search_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введите название аниме для поиска:",
        reply_markup=inline.back_button()
    )
    await state.set_state(SearchState.waiting_for_title)


@router.message(StateFilter(SearchState.waiting_for_title))
async def process_search(message: types.Message, state: FSMContext):
    query = message.text
    msg = await message.answer("🔎 Ищу...")

    results = await parser.search_anime(query)

    if not results:
        await msg.edit_text(
            "Ничего не найдено 😔 Попробуйте другое название.",
            reply_markup=inline.back_button()
        )
        return

    data_storage = {res['url']: res for res in results}
    await state.update_data(search_res=data_storage)

    await msg.edit_text(
        f"Найдены результаты по запросу '{query}':\n"
        "Нажмите на кнопку, чтобы подписаться.",
        reply_markup=inline.search_results(results)
    )


# --- ПОДПИСКА ---
@router.callback_query(F.data.startswith("sub|"))
async def cb_subscribe(callback: types.CallbackQuery, state: FSMContext):
    url = callback.data.split("sub|")[1]
    fsm_data = await state.get_data()
    search_res = fsm_data.get("search_res", {})
    anime_data = search_res.get(url)

    if not anime_data:
        await callback.answer("Данные устарели, повторите поиск", show_alert=True)
        return

    user = await db.get_user(callback.from_user.id)
    preferred_vo = user.favorite_voiceover if user else "Все"

    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=anime_data['title'],
        url=anime_data['url'],
        last_ep=anime_data['last_ep'],
        voiceover=preferred_vo
    )

    if success:
        await callback.answer("✅ Подписка оформлена!", show_alert=True)
    else:
        await callback.answer("⚠️ Вы уже подписаны на это аниме", show_alert=True)

    await state.clear()
    await cb_my_subs(callback)  # Перекидываем в список подписок


@router.callback_query(F.data == "cancel_search")
async def cb_cancel_search(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await cb_back_home(callback, state)


# --- МОИ ПОДПИСКИ ---
@router.callback_query(F.data == "my_subs")
async def cb_my_subs(callback: types.CallbackQuery):
    subs = await db.get_user_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.edit_text(
            "У вас пока нет подписок. Нажмите 'Поиск аниме' чтобы добавить.",
            reply_markup=inline.back_button()
        )
        return

    await callback.message.edit_text(
        "📋 Ваши подписки (нажмите, чтобы удалить):",
        reply_markup=inline.subs_list(subs)
    )


@router.callback_query(F.data.startswith("unsub_"))
async def cb_unsubscribe(callback: types.CallbackQuery):
    sub_id = int(callback.data.split("unsub_")[1])
    await db.delete_subscription(sub_id)
    await callback.answer("🗑 Подписка удалена")
    await cb_my_subs(callback)