from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔥 Свежие серии (Любимая)", callback_data="get_updates_default")
    kb.button(text="🎙 Другая озвучка", callback_data="select_other_vo")
    kb.button(text="📅 Расписание (Добавить)", callback_data="open_schedule")
    kb.button(text="📋 Мои подписки", callback_data="my_subs")
    kb.button(text="⚙️ Настройки любимой", callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()


def voiceover_selection(current_vo: str, mode: str = "save"):
    """
    mode: 'save' - сохранить в БД как любимую
    mode: 'view' - просто посмотреть обновления
    """
    vos = ['AniLiberty', 'Дубляж', 'AniDUB', 'Dream Cast', 'SHIZA Project', 'Субтитры', 'Все']
    kb = InlineKeyboardBuilder()
    for vo in vos:
        text = f"✅ {vo}" if vo == current_vo and mode == 'save' else vo
        # Передаем режим в callback data
        kb.button(text=text, callback_data=f"set_vo_{mode}_{vo}")

    kb.adjust(2)
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()


def updates_list_actions(anime_list: list):
    """
    Генерирует компактные кнопки-цифры: [1] [2] [3] [4] [5]
    """
    kb = InlineKeyboardBuilder()

    # Создаем кнопки только с цифрами
    for index in range(len(anime_list)):
        kb.button(
            text=str(index + 1),
            callback_data=f"add_from_list_{index}"
        )

    kb.adjust(5)

    control_kb = InlineKeyboardBuilder()
    control_kb.button(text="🔄 Обновить", callback_data="refresh_updates")
    control_kb.button(text="🔙 В меню", callback_data="back_home")
    control_kb.adjust(2)

    kb.attach(control_kb)

    return kb.as_markup()


def search_results(results: list):
    kb = InlineKeyboardBuilder()
    for anime in results:
        short_title = anime['title'][:20]
        kb.button(text=f"➕ {short_title}", callback_data=f"sub|{anime['url']}"[:64])
    kb.adjust(1)
    kb.button(text="❌ Отмена", callback_data="cancel_search")
    return kb.as_markup()


def subs_list_actions(subscriptions: list):
    """
    Генерирует кнопки-цифры для удаления подписок: [1] [2] [3]
    """
    kb = InlineKeyboardBuilder()

    for index, sub in enumerate(subscriptions):
        kb.button(
            text=str(index + 1),
            callback_data=f"unsub_{sub.id}"
        )

    kb.adjust(5)
    control_kb = InlineKeyboardBuilder()
    control_kb.button(text="🔙 Назад", callback_data="back_home")
    kb.attach(control_kb)
    return kb.as_markup()


def schedule_list_actions(items_count: int):
    """
    Кнопки-цифры для выбора аниме из расписания.
    """
    kb = InlineKeyboardBuilder()
    for index in range(items_count):
        kb.button(text=str(index + 1), callback_data=f"sched_sel_{index}")

    kb.adjust(5)
    kb.attach(InlineKeyboardBuilder().button(text="🔙 В меню", callback_data="back_home"))
    return kb.as_markup()


def schedule_day_view(day_index: int, total_days: int, items_count: int):
    """
    Клавиатура расписания с навигацией по дням.
    [ ⬅️ ] [ День X ] [ ➡️ ]
    [ 1 ] [ 2 ] [ 3 ] [ 4 ] [ 5 ] ...
    [ В меню ]
    """
    kb = InlineKeyboardBuilder()

    # 1. Строка навигации
    prev_idx = day_index - 1 if day_index > 0 else total_days - 1
    next_idx = day_index + 1 if day_index < total_days - 1 else 0

    kb.button(text="⬅️", callback_data=f"sched_day_{prev_idx}")
    kb.button(text=f"{day_index + 1} / {total_days}", callback_data="ignore")  # Просто счетчик, не кликабельный
    kb.button(text="➡️", callback_data=f"sched_day_{next_idx}")

    # 2. Сетка кнопок аниме
    for i in range(items_count):
        kb.button(text=str(i + 1), callback_data=f"sched_item_{i}")

    # Настраиваем сетку:
    # Первая строка - 3 кнопки (Навигация)
    # Остальные - по 5 кнопок (Аниме)
    # Последняя - 1 (Меню)
    sizes = [3] + [5] * ((items_count + 4) // 5) + [1]
    kb.adjust(*sizes)

    kb.button(text="🔙 В меню", callback_data="back_home")

    return kb.as_markup()


def anime_voiceovers_list(voiceovers: list):
    """
    Кнопки выбора озвучки (для нового сообщения).
    """
    kb = InlineKeyboardBuilder()
    for vo in voiceovers:
        # Обрезаем название, чтобы влезло в callback_data (макс 64 байта)
        kb.button(text=vo, callback_data=f"sched_sub_vo_{vo[:40]}")

    kb.adjust(2)
    kb.attach(InlineKeyboardBuilder().button(text="❌ Отмена", callback_data="cancel_schedule"))
    return kb.as_markup()


def back_button():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()