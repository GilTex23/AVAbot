import os
import psutil
import logging
import glob
import zipfile
from io import BytesIO
from datetime import datetime, timedelta
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
    await callback.answer()


@router.callback_query(F.data == "admin_close")
async def cb_admin_close(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("❌ Админ-панель закрыта.")


# --- СТАТИСТИКА ---
@router.callback_query(F.data == "admin_stats")
async def cb_stats(callback: types.CallbackQuery):
    await callback.answer()
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
    await callback.answer()
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    text = (
        f"🖥 <b>Состояние сервера:</b>\n\n"
        f"🧠 CPU: {cpu}%\n"
        f"💾 RAM: {ram.percent}% ({ram.used // 1024 // 1024}MB / {ram.total // 1024 // 1024}MB)\n"
        f"💿 Disk: {disk.percent}% ({disk.free // 1024 // 1024 // 1024}GB / {disk.total // 1024 // 1024 // 1024}GB free)"
    )
    await callback.message.edit_text(text, reply_markup=admin_kb.back_to_admin(), parse_mode="HTML")


# --- ЛОГИ: ГЛАВНОЕ МЕНЮ ---
@router.callback_query(F.data == "admin_logs")
async def cb_logs_menu(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🪵 <b>Управление логами</b>\nВыберите тип логов:",
        reply_markup=admin_kb.admin_logs_menu(),
        parse_mode="HTML"
    )


# --- ЛОГИ: ВЫБОР ПЕРИОДА ---
@router.callback_query(F.data.startswith("logs_type_"))
async def cb_logs_period(callback: types.CallbackQuery):
    log_type = callback.data.split("_")[-1]  # bot или error
    name = "Bot Logs" if log_type == "bot" else "Error Logs"

    await callback.message.edit_text(
        f"📂 <b>{name}</b>\nВыберите период:",
        reply_markup=admin_kb.admin_logs_period(log_type),
        parse_mode="HTML"
    )


# --- ЛОГИ: ОТПРАВКА ---
@router.callback_query(F.data.startswith("get_log_"))
async def cb_get_logs(callback: types.CallbackQuery, state: FSMContext):
    # format: get_log_{type}_{period}
    parts = callback.data.split("_")
    log_type = parts[2]
    period = parts[3]

    base_filename = "bot.log" if log_type == "bot" else "errors.log"
    log_dir = "logs"

    await callback.answer("⏳ Собираю данные...")

    # --- ВСЕ ФАЙЛЫ (ZIP) ---
    if period == "all":
        # Собираем все файлы маски (bot.log*) в архив
        memory_file = BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            # Текущий файл
            if os.path.exists(os.path.join(log_dir, base_filename)):
                zf.write(os.path.join(log_dir, base_filename), base_filename)

            # Ротированные файлы (bot.log.2023-10-10)
            for file_path in glob.glob(os.path.join(log_dir, f"{base_filename}.*")):
                zf.write(file_path, os.path.basename(file_path))

        memory_file.seek(0)
        input_file = types.BufferedInputFile(memory_file.read(), filename=f"{log_type}_all_logs.zip")
        await callback.message.answer_document(input_file, caption=f"📦 Все логи ({log_type})")
        return

    # --- КАСТОМНАЯ ДАТА ---
    if period == "custom":
        await callback.message.edit_text(
            "📆 Введите дату в формате <code>YYYY-MM-DD</code> (например, 2023-10-25):",
            reply_markup=admin_kb.back_to_admin(),  # Или кнопка отмены
            parse_mode="HTML"
        )
        await state.update_data(log_type=log_type)
        await state.set_state(AdminState.waiting_for_log_date)  # Нужно добавить это состояние в utils/states.py
        return

    # --- СБОР ФАЙЛОВ ПО ДАТАМ ---
    files_to_send = []
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Список дат, которые нам нужны
    target_dates = []

    if period == "today":
        target_dates.append(today_str)
    elif period == "yesterday":
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        target_dates.append(yesterday)
    elif period == "3days":
        for i in range(3):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            target_dates.append(d)

    # Ищем файлы
    content = ""
    for date_str in target_dates:
        # Если дата = сегодня, читаем основной файл (bot.log), НО
        # TimedRotatingFileHandler пишет в основной файл только сегодняшние логи.
        # Вчерашние он переименовывает в bot.log.YYYY-MM-DD.

        file_path = ""
        if date_str == today_str:
            file_path = os.path.join(log_dir, base_filename)
        else:
            file_path = os.path.join(log_dir, f"{base_filename}.{date_str}")

        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                    if file_content:
                        content += f"\n\n--- LOGS FOR {date_str} ---\n{file_content}"
            except Exception as e:
                content += f"\nError reading {date_str}: {e}"

    if not content.strip():
        await callback.message.answer("📭 Логи за этот период пусты или не найдены.")
        return

    # Отправляем файл
    # Если файл слишком большой, лучше отправить его как документ
    file_bytes = content.encode("utf-8")
    input_file = types.BufferedInputFile(file_bytes, filename=f"{log_type}_{period}.log")

    await callback.message.answer_document(input_file, caption=f"📄 Логи: {log_type} ({period})")


# --- ОБРАБОТКА ВВОДА ДАТЫ ---
@router.message(StateFilter(AdminState.waiting_for_log_date))
async def msg_log_date(message: types.Message, state: FSMContext):
    date_str = message.text.strip()
    data = await state.get_data()
    log_type = data.get("log_type", "bot")
    base_filename = "bot.log" if log_type == "bot" else "errors.log"
    log_dir = "logs"

    # Проверка формата
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("⚠️ Неверный формат. Используйте YYYY-MM-DD.")
        return

    file_path = os.path.join(log_dir, f"{base_filename}.{date_str}")

    # Если запрашивают сегодня
    if date_str == datetime.now().strftime("%Y-%m-%d"):
        file_path = os.path.join(log_dir, base_filename)

    if os.path.exists(file_path):
        fs_file = FSInputFile(file_path, filename=f"{log_type}_{date_str}.log")
        await message.answer_document(fs_file, caption=f"📄 Логи за {date_str}")
    else:
        await message.answer(f"📭 Файл логов за {date_str} не найден.")

    await state.clear()


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
    await callback.answer()
    await state.update_data(callb_msg_id=callback.message.message_id, callb_chat_id=callback.message.chat.id)
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
    data = await state.get_data()

    await state.update_data(msg_id=message.message_id, from_chat=message.chat.id)

    try:
        await message.bot.edit_message_text("📢 <b>Рассылка</b>\n\n"
            "Следуйте инструкциям далее...",
            chat_id=data.get("callb_chat_id"),
            message_id=data.get("callb_msg_id"),
            reply_markup=None,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning("Error edit message: State may be empty.")

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

    await callback.answer("⏳ Рассылка началась...")
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
        f"🚫 Не доставлено (блок): {blocked}",
        reply_markup=admin_kb.back_to_admin()
    )
    await state.clear()


# --- SQL QUERY ---
@router.callback_query(F.data == "admin_sql")
async def cb_sql_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
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