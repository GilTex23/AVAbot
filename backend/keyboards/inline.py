from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config


FAVORITES_PAGE_SIZE = 10
# Контекст экрана любимых озвучек: знакомство после /start или настройки из меню
FAVORITES_ONBOARDING = "o"
FAVORITES_SETTINGS = "s"


APP_BUTTON_TEXT = "📱 Открыть приложение"


def _add_app_button(kb: InlineKeyboardBuilder) -> bool:
    """Кнопка мини-аппа, если задан MINIAPP_URL; True — если добавлена"""
    if not config.MINIAPP_URL:
        return False
    kb.button(text=APP_BUTTON_TEXT, web_app=WebAppInfo(url=config.MINIAPP_URL))
    return True


def main_menu(has_favorites: bool = False):
    kb = InlineKeyboardBuilder()
    _add_app_button(kb)
    kb.button(text="🔥 Свежие серии (любимые)" if has_favorites else "🔥 Свежие серии (все озвучки)", callback_data="get_updates_default")
    kb.button(text="🎙 Другая озвучка", callback_data="select_other_vo")
    kb.button(text="📅 Расписание (Добавить)", callback_data="open_schedule")
    kb.button(text="📋 Мои подписки", callback_data="my_subs")
    if config.YUMMY_ENABLED:
        kb.button(text="🔍 Найти на YummyAnime", callback_data="yummy_find")
    kb.button(text="⚙️ Любимые озвучки", callback_data="settings")
    kb.adjust(1)
    return kb.as_markup()


def yummy_results(results: list[dict]):
    """Результаты поиска на YummyAnime; в callback_data — id тайтла"""
    kb = InlineKeyboardBuilder()
    for index, item in enumerate(results):
        kb.button(text=f"{index + 1}. {item['title'][:40]}", callback_data=f"yt:{item['id']}")
    kb.adjust(1)
    kb.attach(InlineKeyboardBuilder().button(text="🔙 В меню", callback_data="back_home"))
    return kb.as_markup()


def yummy_voiceovers(dubs: list[dict], url: str):
    """Озвучки тайтла YummyAnime с последней серией; в callback_data — номер в списке из FSM"""
    kb = InlineKeyboardBuilder()
    for index, dub in enumerate(dubs):
        kb.button(text=f"{dub['name']} · {dub['last_episode']}", callback_data=f"ysub:{index}")
    kb.adjust(2)
    controls = InlineKeyboardBuilder()
    controls.button(text="🔗 Открыть на YummyAnime", url=url)
    controls.button(text="❌ Отмена", callback_data="close_message")
    controls.adjust(1)
    kb.attach(controls)
    return kb.as_markup()


def welcome():
    """После первого /start: приложение, меню в чате или сразу любимые озвучки"""
    kb = InlineKeyboardBuilder()
    _add_app_button(kb)
    kb.button(text="💬 Меню в чате", callback_data="back_home")
    kb.button(text="🎙 Выбрать любимые озвучки", callback_data=f"fav:p:0:{FAVORITES_ONBOARDING}")
    kb.adjust(1)
    return kb.as_markup()


def open_app():
    kb = InlineKeyboardBuilder()
    _add_app_button(kb)
    kb.button(text="💬 Меню в чате", callback_data="back_home")
    kb.adjust(1)
    return kb.as_markup()


def favorite_voiceovers(catalog: list[dict], favorites: list[str], page: int, context: str):
    """
    Отметки любимых озвучек из справочника, по FAVORITES_PAGE_SIZE на страницу.
    В callback_data — id озвучки, а не название: у Telegram лимит 64 байта.
    """
    pages = max(1, -(-len(catalog) // FAVORITES_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    chosen = set(favorites)

    kb = InlineKeyboardBuilder()
    items = InlineKeyboardBuilder()
    for item in catalog[page * FAVORITES_PAGE_SIZE:(page + 1) * FAVORITES_PAGE_SIZE]:
        mark = "✅ " if item["name"] in chosen else ""
        items.button(text=f"{mark}{item['name']}", callback_data=f"fav:t:{item['id']}:{page}:{context}")
    items.adjust(2)
    kb.attach(items)

    if pages > 1:
        nav = InlineKeyboardBuilder()
        nav.button(text="⬅️", callback_data=f"fav:p:{(page - 1) % pages}:{context}")
        nav.button(text=f"{page + 1} / {pages}", callback_data="ignore")
        nav.button(text="➡️", callback_data=f"fav:p:{(page + 1) % pages}:{context}")
        nav.adjust(3)
        kb.attach(nav)

    controls = InlineKeyboardBuilder()
    if favorites:
        controls.button(text="♻️ Сбросить — все озвучки", callback_data=f"fav:c:{page}:{context}")
    controls.button(text="✅ Готово" if context == FAVORITES_ONBOARDING else "🔙 Назад", callback_data="back_home")
    controls.adjust(1)
    kb.attach(controls)
    return kb.as_markup()


def feed_voiceovers(studios: list[dict]):
    """Озвучки, которые сейчас есть в ленте; в callback_data — номер в списке, сохранённом в FSM"""
    kb = InlineKeyboardBuilder()
    for index, studio in enumerate(studios):
        kb.button(text=f"{studio['name']} ({studio['count']})", callback_data=f"vo_view:{index}")
    kb.adjust(2)

    controls = InlineKeyboardBuilder()
    controls.button(text="🌐 Все озвучки", callback_data="vo_view:all")
    controls.button(text="🔙 Назад", callback_data="back_home")
    controls.adjust(1)
    kb.attach(controls)
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
    kb_up = InlineKeyboardBuilder()
    kb_middle = InlineKeyboardBuilder()
    kb_down = InlineKeyboardBuilder()

    # 1. Строка навигации
    prev_idx = day_index - 1 if day_index > 0 else total_days - 1
    next_idx = day_index + 1 if day_index < total_days - 1 else 0

    kb_up.button(text="⬅️", callback_data=f"sched_day_{prev_idx}")
    kb_up.button(text=f"{day_index + 1} / {total_days}", callback_data="ignore")
    kb_up.button(text="➡️", callback_data=f"sched_day_{next_idx}")

    # 2. Сетка кнопок аниме
    for i in range(items_count):
        kb_middle.button(text=str(i + 1), callback_data=f"sched_item_{i}")

    kb_down.button(text="🔙 В меню", callback_data="back_home")

    # Настраиваем сетку:
    # Первая строка - 3 кнопки (Навигация)
    # Остальные - по 5 кнопок (Аниме)
    # Последняя - 1 (Меню)

    kb_up.adjust(3)
    kb_middle.adjust(5)
    kb_down.adjust(1)

    kb.attach(kb_up)
    kb.attach(kb_middle)
    kb.attach(kb_down)

    return kb.as_markup()


def anime_voiceovers_list(voiceovers: list, url: str | None = None):
    """
    Кнопки выбора озвучки (для нового сообщения).
    """
    kb = InlineKeyboardBuilder()
    for index, vo in enumerate(voiceovers):
        # Название может не влезть в callback_data (64 байта) — передаём номер, список лежит в FSM
        kb.button(text=vo, callback_data=f"sched_sub_vo:{index}")

    kb.adjust(2)
    controls = InlineKeyboardBuilder()
    if url:
        controls.button(text="🔗 Открыть на AnimeGO", url=url)
    controls.button(text="❌ Отмена", callback_data="close_message")
    controls.adjust(1)
    kb.attach(controls)
    return kb.as_markup()


def back_button():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="back_home")
    return kb.as_markup()