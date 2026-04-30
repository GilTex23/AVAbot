from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="🖥 Сервер", callback_data="admin_server")
    kb.button(text="📢 Рассылка", callback_data="admin_broadcast")
    kb.button(text="🪵 Логи", callback_data="admin_logs")
    kb.button(text="🔄 Force Check", callback_data="admin_force_check")
    kb.button(text="🗄 SQL Query", callback_data="admin_sql")
    kb.button(text="❌ Закрыть", callback_data="admin_close")
    kb.adjust(2)
    return kb.as_markup()


def broadcast_confirm():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="broadcast_send")
    kb.button(text="❌ Отмена", callback_data="admin_back")
    kb.adjust(2)
    return kb.as_markup()


def back_to_admin():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад в админку", callback_data="admin_back")
    return kb.as_markup()


def admin_logs_menu():
    kb = InlineKeyboardBuilder()
    # Тип логов
    kb.button(text="📄 Bot Logs (Info)", callback_data="logs_type_bot")
    kb.button(text="❌ Error Logs", callback_data="logs_type_error")
    kb.adjust(2)
    kb.attach(InlineKeyboardBuilder().button(text="🔙 Назад в админку", callback_data="admin_back"))
    return kb.as_markup()


def admin_logs_period(log_type: str):
    """
    Клавиатура выбора периода.
    log_type: 'bot' или 'error'
    """
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сегодня", callback_data=f"get_log_{log_type}_today")
    kb.button(text="🕚 Вчера", callback_data=f"get_log_{log_type}_yesterday")
    kb.button(text="🗓 Последние 3 дня", callback_data=f"get_log_{log_type}_3days")
    kb.button(text="📆 Выбрать дату", callback_data=f"get_log_{log_type}_custom")
    kb.button(text="📁 Скачать всё (ZIP)", callback_data=f"get_log_{log_type}_all")
    kb.adjust(2)
    kb.attach(InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="admin_logs"))
    return kb.as_markup()
