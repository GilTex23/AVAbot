from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Поиск аниме", callback_data="search_anime")
    kb.button(text="📋 Мои подписки", callback_data="my_subs")
    kb.button(text="⚙️ Настройки", callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()

def voiceover_selection(current_vo: str):
    vos = ['AniLibria', 'AniDUB', 'Dream Cast', 'SHIZA Project', 'Субтитры', 'Все']
    kb = InlineKeyboardBuilder()
    for vo in vos:
        text = f"✅ {vo}" if vo == current_vo else vo
        kb.button(text=text, callback_data=f"set_vo_{vo}")
    kb.adjust(2)
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()

def search_results(results: list):
    """Генерирует кнопки для найденных аниме"""
    kb = InlineKeyboardBuilder()
    for anime in results:
        short_title = anime['title'][:20]
        kb.button(
            text=f"➕ {short_title}",
            # Передадим URL в колбэке (надеясь что он влезет) или используем MemoryStorage позже
            callback_data=f"sub|{anime['url']}"[:64]
        )
    kb.adjust(1)
    kb.button(text="❌ Отмена", callback_data="cancel_search")
    return kb.as_markup()

def subs_list(subscriptions: list):
    kb = InlineKeyboardBuilder()
    for sub in subscriptions:
        kb.button(
            text=f"🗑 {sub.anime_title[:20]}",
            callback_data=f"unsub_{sub.id}"
        )
    kb.adjust(1)
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()

def back_button():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()