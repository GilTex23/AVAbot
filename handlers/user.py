from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext

from database import requests as db
from keyboards import inline
from services import parser
from utils.states import SearchState

router = Router()


# --- СТАРТ И МЕНЮ ---
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"!Привет, {message.from_user.first_name}! 👋\n"
        "Я помогу тебе не пропустить выход новых серий.\n\n"
        "1. Нажми <b>Поиск аниме</b>\n"
        "2. Введи название\n"
        "3. Выбери из списка, чтобы подписаться",
        reply_markup=inline.main_menu(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "back_home")
async def cb_back_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Главное меню:",
        reply_markup=inline.main_menu()
    )


# --- НАСТРОЙКИ (Озвучка) ---
@router.callback_query(F.data == "settings")
async def cb_settings(callback: types.CallbackQuery):
    user_vo = await db.get_user_voiceover(callback.from_user.id)
    await callback.message.edit_text(
        f"Текущая любимая озвучка: <b>{user_vo}</b>\n"
        "Бот будет присылать уведомления, только если выйдет серия в этой озвучке (или выбери 'Все').",
        reply_markup=inline.voiceover_selection(user_vo),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("set_vo_"))
async def cb_set_vo(callback: types.CallbackQuery):
    new_vo = callback.data.split("set_vo_")[1]
    await db.update_user_voiceover(callback.from_user.id, new_vo)
    await callback.answer(f"✅ Озвучка изменена на {new_vo}")
    await cb_settings(callback)


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
    # Извлекаем URL из колбэка
    url = callback.data.split("sub|")[1]

    # Достаем полные данные из FSM
    fsm_data = await state.get_data()
    search_res = fsm_data.get("search_res", {})

    anime_data = search_res.get(url)

    if not anime_data:
        await callback.answer("Данные устарели, повторите поиск", show_alert=True)
        return

    # Добавляем в БД
    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=anime_data['title'],
        url=anime_data['url'],
        last_ep=anime_data['last_ep']
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