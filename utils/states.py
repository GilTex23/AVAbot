from aiogram.fsm.state import StatesGroup, State

class SearchState(StatesGroup):
    waiting_for_title = State()

class UpdatesState(StatesGroup):
    viewing_list = State()