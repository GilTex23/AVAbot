from aiogram.fsm.state import StatesGroup, State

class SearchState(StatesGroup):
    waiting_for_title = State()

class UpdatesState(StatesGroup):
    viewing_list = State()

class AdminState(StatesGroup):
    waiting_for_broadcast_content = State() # Ждем контент для рассылки
    waiting_for_broadcast_confirm = State() # Ждем подтверждения
    waiting_for_sql_query = State()         # Ждем SQL запрос