from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from database.models import User, Subscription
import config

# Логика авторизации
class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        username, password = form.get("username"), form.get("password")

        # Проверка логина и пароля из .env
        if username == config.ADMIN_PANEL_USER and password == config.ADMIN_PANEL_PASS:
            # Устанавливаем токен сессии
            request.session.update({"token": "admin_token_auth_success"})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        # Очищаем сессию при выходе
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        # Проверяем, есть ли токен в сессии (залогинен ли пользователь)
        token = request.session.get("token")
        if not token:
            return False
        return token == "admin_token_auth_success"

# Инициализация бэкенда авторизации
authentication_backend = AdminAuth(secret_key=config.ADMIN_PANEL_SECRET)


# Настройка отображения таблицы Users
class UserAdmin(ModelView, model=User):
    column_list = [User.id, User.username, User.favorite_voiceover, User.registered_at]
    column_searchable_list = [User.id, User.username]
    column_sortable_list = [User.registered_at, User.id]
    column_default_sort = ("registered_at", True)
    name = "Пользователь"
    name_plural = "Пользователи"
    icon = "fa-solid fa-user"


# Настройка отображения таблицы Subscriptions
class SubscriptionAdmin(ModelView, model=Subscription):
    column_list = [
        Subscription.id,
        Subscription.user_id,
        Subscription.anime_title,
        Subscription.voiceover,
        Subscription.last_episode
    ]
    column_searchable_list = [Subscription.anime_title, Subscription.user_id]
    column_sortable_list = [Subscription.id, Subscription.user_id]
    name = "Подписка"
    name_plural = "Подписки"
    icon = "fa-solid fa-bell"