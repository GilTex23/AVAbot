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
