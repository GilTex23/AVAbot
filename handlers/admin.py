import os
import psutil
import logging
from aiogram import Router, F, types
from aiogram.filters import Command, StateFilter, Filter
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile

import config
from database import requests as db
from keyboards import admin_kb
from services.checker import check_updates
from utils.states import AdminState

router = Router()
logger = logging.getLogger(__name__)


# --- ФИЛЬТР АДМИНА ---
class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in config.ADMIN_IDS


# Применяем фильтр ко всему роутеру (чтобы обычные юзеры даже не триггерили эти хендлеры)
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# --- ГЛАВНОЕ МЕНЮ ---
@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Добро пожаловать в панель управления.",
        reply_markup=admin_kb.admin_main_menu()
    )


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👋 Панель управления.",
        reply_markup=admin_kb.admin_main_menu()
    )


@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: types.CallbackQuery):
    await callback.message.delete()


# --- СТАТИСТИКА ---
@router.callback_query(F.data == "admin_stats")
async def cb_stats(callback: types.CallbackQuery):
    stats = await db.get_bot_stats()

    top_text = "\n".join([f"• {t[0]}: {t[1]}" for t in stats['top_anime']])

    text = (
        f"📊 <b>Статистика бота:</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['users']}</b>\n"
        f"🆕 За 24 часа: <b>{stats['new_users']}</b>\n"
        f"📑 Активных подписок: <b>{stats['subs']}</b>\n\n"
        f"🏆 <b>Топ-3 подписок:</b>\n{top_text}"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb.back_to_admin(), parse_mode="HTML")


# --- СЕРВЕР ---
@router.callback_query(F.data == "admin_server")
async def cb_server(callback: types.CallbackQuery):
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    text = (
        f"🖥 <b>Состояние сервера:</b>\n\n"
        f"🧠 CPU: {cpu}%\n"
        f"💾 RAM: {ram.percent}% ({ram.used // 1024 // 1024}MB / {ram.total // 1024 // 1024}MB)\n"
        f"💿 Disk: {disk.percent}% ({disk.free // 1024 // 1024 // 1024}/{disk.used // 1024 // 1024 // 1024}GB free)"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb.back_to_admin(), parse_mode="HTML")


# --- ЛОГИ ---
@router.callback_query(F.data == "admin_logs")
async def cb_logs(callback: types.CallbackQuery):
    await callback.answer("Отправляю логи...")
    try:
        log_file = FSInputFile("logs/bot.log")
        await callback.message.answer_document(log_file, caption="📄 Bot Logs")

        if os.path.exists("logs/errors.log"):
            err_file = FSInputFile("logs/errors.log")
            await callback.message.answer_document(err_file, caption="❌ Error Logs")
    except Exception as e:
        await callback.message.answer(f"Ошибка при чтении логов: {e}")


# --- FORCE CHECK (Принудительная проверка) ---
@router.callback_query(F.data == "admin_force_check")
async def cb_force_check(callback: types.CallbackQuery):
    await callback.answer("Запускаю проверку...", show_alert=False)
    await callback.message.answer("⏳ Принудительная проверка аниме запущена.")

    try:
        await check_updates(callback.bot)
        await callback.message.answer("✅ Проверка завершена.")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка проверки: {e}")


# --- РАССЫЛКА (BROADCAST) ---
@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение (текст, фото, видео), которое вы хотите разослать всем пользователям.\n"
        "Можно переслать сообщение из другого чата.",
        reply_markup=admin_kb.back_to_admin(),
        parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_broadcast_content)


@router.message(StateFilter(AdminState.waiting_for_broadcast_content))
async def msg_broadcast_content(message: types.Message, state: FSMContext):
    # Копируем сообщение, чтобы показать админу превью
    # Используем copy_to, чтобы сохранить форматирование и медиа
    await message.copy_to(chat_id=message.chat.id)

    await state.update_data(msg_id=message.message_id, from_chat=message.chat.id)

    await message.answer(
        "👆 Вот так будет выглядеть сообщение.\nПодтверждаете рассылку?",
        reply_markup=admin_kb.broadcast_confirm()
    )
    await state.set_state(AdminState.waiting_for_broadcast_confirm)


@router.callback_query(F.data == "broadcast_send", StateFilter(AdminState.waiting_for_broadcast_confirm))
async def cb_broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("msg_id")
    from_chat = data.get("from_chat")

    await callback.message.edit_text("⏳ Рассылка началась...")

    users = await db.get_all_users_ids()
    count = 0
    blocked = 0

    for user_id in users:
        try:
            await callback.bot.copy_message(
                chat_id=user_id,
                from_chat_id=from_chat,
                message_id=msg_id
            )
            count += 1
        except Exception as e:
            blocked += 1

    await callback.message.answer(
        f"✅ Рассылка завершена!\n"
        f"📨 Отправлено: {count}\n"
        f"🚫 Недоставлено (блок): {blocked}",
        reply_markup=admin_kb.back_to_admin()
    )
    await state.clear()


# --- SQL QUERY ---
@router.callback_query(F.data == "admin_sql")
async def cb_sql_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🗄 <b>SQL Mode</b>\n\n"
        "Введите SQL запрос. \n"
        "⚠️ <b>ОСТОРОЖНО!</b> Запрос выполняется напрямую к БД.",
        reply_markup=admin_kb.back_to_admin(),
        parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_sql_query)


@router.message(StateFilter(AdminState.waiting_for_sql_query))
async def msg_sql_exec(message: types.Message, state: FSMContext):
    query = message.text
    result = await db.execute_raw_sql(query)

    if isinstance(result, list):
        if not result:
            res_text = "Результат пуст []."
        else:
            res_text = "\n".join([str(row) for row in result])
    else:
        res_text = str(result)

    if len(res_text) > 3900:
        res_text = res_text[:3900] + "... (обрезано)"
    res_text += f"```\n{res_text}\n```\nОжидается следующий запрос..."

    await message.answer(res_text, parse_mode="Markdown")