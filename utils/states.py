from aiogram.fsm.state import StatesGroup, State

class SearchState(StatesGroup):
    waiting_for_title = State()

class UpdatesState(StatesGroup):
    viewing_list = State()

class AdminState(StatesGroup):
    waiting_for_broadcast_content = State()
    waiting_for_broadcast_confirm = State()
    waiting_for_sql_query = State()
    waiting_for_log_date = State()