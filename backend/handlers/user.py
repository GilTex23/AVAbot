from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
from contextlib import suppress
import html

from database import requests as db
from keyboards import inline
from services import parser, stats, voiceovers
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


# --- СТАРТ ---
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    is_new_user = await db.add_user(message.from_user.id, message.from_user.username)

    if is_new_user:
        text, kb = await favorites_screen(message.from_user.id, page=0, context=inline.FAVORITES_ONBOARDING)
        await message.answer(
            f"👋 Привет, {html.escape(message.from_user.first_name or '')}!\n\n" + text,
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await render_main_menu(message, message.from_user.id, is_edit=False)


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

    schedule_days = await parser.get_schedule(callback.bot)

    if schedule_days is None:
        await callback.message.edit_text(
            "⚠️ Ошибка получения расписания. Попробуйте позже.",
            reply_markup=inline.back_button()
        )
        return

    # Время и дни — в часовом поясе из настроек мини-аппа (по умолчанию Москва)
    user = await db.get_user(callback.from_user.id)
    schedule_days = parser.localize_schedule(schedule_days, parser.zone_or_moscow(user.quiet_timezone if user else None))

    await state.update_data(schedule_days=schedule_days, current_day_index=0)
    await state.set_state(ScheduleState.viewing_schedule)

    await render_schedule_day(callback.message, state)


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

    info = await parser.get_anime_details(anime['link'], callback.bot)

    if not info:
        await callback.answer("❌ Ошибка получения данных", show_alert=True)
        await msg.edit_text("❌ Ошибка получения данных")
        return

    # 2. Проверки (то же правило, что в мини-аппе; из расписания подписка начинается с серии 0)
    reason = subscription_block_reason(info, "Серия 0")
    if reason:
        await msg.edit_text(
            f"⛔️ Нельзя добавить <b>{anime['title']}</b>.\nПричина: {reason}",
            parse_mode="HTML"
        )
        return

    anime_voiceovers = info.get('available_voiceovers', [])
    if not anime_voiceovers:
        await msg.edit_text(f"⚠️ Нет озвучек для <b>{anime['title']}</b>.", parse_mode="HTML")
        return

    await state.update_data(
        selected_anime_title=anime['title'],
        selected_anime_url=anime['link'],
        selected_anime_total=info['total_episodes'],
        selected_anime_voiceovers=anime_voiceovers,
    )

    await msg.edit_text(
        f"📺 <b>{anime['title']}</b>\n"
        f"👇 Выберите озвучку для подписки:",
        reply_markup=inline.anime_voiceovers_list(anime_voiceovers),
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

    success = await db.add_subscription(
        tg_id=callback.from_user.id,
        title=title,
        url=url,
        last_ep="Серия 0",
        voiceover=vo,
        total_eps=total_eps
    )

    total_str = total_eps if total_eps else "?"

    if success:
        await stats.increment("subscriptions.created", stats.SOURCE_BOT)
        await callback.message.edit_text(
            f"✅ <b>Подписка оформлена!</b>\n\n"
            f"📺 {title}\n"
            f"🎙 {vo}\n"
            f"📊 Эпизоды: ? / {total_str}",
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
    subs = await db.get_user_subscriptions(callback.from_user.id)

    if not subs:
        await callback.message.edit_text(
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
