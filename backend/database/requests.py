from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select, update, delete, and_, func, text
from sqlalchemy.orm import joinedload
from database.models import Base, User, Subscription
import datetime
import config

engine = create_async_engine(config.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    """Keep a lightweight startup DB check; schema changes are handled by Alembic."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


# --- USER ---
async def get_user(tg_id: int):
    async with async_session() as session:
        return await session.scalar(select(User).where(User.id == tg_id))


async def add_user(tg_id: int, username: str):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        if not user:
            session.add(User(id=tg_id, username=username, favorite_voiceover=None))
            await session.commit()
            return True
        return False


async def upsert_user_profile(tg_id: int, username: str | None = None, photo_url: str | None = None):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        if not user:
            user = User(id=tg_id, username=username, photo_url=photo_url, favorite_voiceover=None)
            session.add(user)
        else:
            if username is not None:
                user.username = username
            if photo_url is not None:
                user.photo_url = photo_url

        await session.commit()
        await session.refresh(user)
        return user


async def update_user_voiceover(tg_id: int, vo: str):
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == tg_id)
            .values(favorite_voiceover=vo)
        )
        await session.commit()


async def update_user_quiet_hours(
    tg_id: int,
    enabled: bool,
    start: str,
    end: str,
    timezone: str,
):
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == tg_id)
            .values(
                quiet_hours_enabled=enabled,
                quiet_hours_start=start,
                quiet_hours_end=end,
                quiet_timezone=timezone,
            )
        )
        await session.commit()


async def get_user_voiceover(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        return user.favorite_voiceover if user else "AniLiberty"


# --- SUBSCRIPTIONS ---
async def add_subscription(tg_id: int, title: str, url: str, last_ep: str, voiceover: str, total_eps: int = None):
    """Добавляет подписку с конкретной озвучкой"""
    async with async_session() as session:
        clean_url = url.split('#')[0].rstrip('/')

        existing = await session.scalar(
            select(Subscription).where(
                and_(
                    Subscription.user_id == tg_id,
                    Subscription.anime_url == clean_url,  # <-- Ищем по чистому URL
                    Subscription.voiceover == voiceover
                )
            )
        )
        if existing:
            return False

        session.add(Subscription(
            user_id=tg_id,
            anime_title=title,
            anime_url=clean_url,
            last_episode=last_ep,
            voiceover=voiceover,
            total_episodes=total_eps
        ))
        await session.commit()
        return True

async def update_total_episodes(sub_id: int, total_eps: int):
    """Обновляет общее количество серий у подписки"""
    async with async_session() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(total_episodes=total_eps)
        )
        await session.commit()


async def get_all_subscriptions():
    """Получить все подписки для чекера (с ЖАДНОЙ подгрузкой User)"""
    async with async_session() as session:
        query = select(Subscription).options(joinedload(Subscription.user))
        result = await session.execute(query)
        # .unique() часто нужен при joinedload, чтобы убрать дубликаты в ORM
        return result.scalars().unique().all()


async def get_user_subscriptions(tg_id: int):
    async with async_session() as session:
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == tg_id)
        )
        return result.scalars().all()


async def delete_subscription(sub_id: int):
    async with async_session() as session:
        await session.execute(delete(Subscription).where(Subscription.id == sub_id))
        await session.commit()


async def update_sub_last_episode(sub_id: int, episode: str):
    async with async_session() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.id == sub_id)
            .values(last_episode=episode)
        )
        await session.commit()


# --- ADMIN FUNCTIONS ---
async def get_bot_stats():
    """Собирает статистику по пользователям и подпискам"""
    async with async_session() as session:
        users_count = await session.scalar(select(func.count(User.id)))

        subs_count = await session.scalar(select(func.count(Subscription.id)))

        day_ago = datetime.datetime.utcnow() - datetime.timedelta(days=1)
        new_users = await session.scalar(select(func.count(User.id)).where(User.registered_at >= day_ago))

        # Топ-3 популярных аниме
        # (Сложный запрос, группировка по названию)
        top_anime = await session.execute(
            select(Subscription.anime_title, func.count(Subscription.user_id).label('count'))
            .group_by(Subscription.anime_title)
            .order_by(text('count DESC'))
            .limit(3)
        )

        return {
            "users": users_count,
            "subs": subs_count,
            "new_users": new_users,
            "top_anime": top_anime.all()
        }


async def get_all_users_ids():
    """Возвращает ID всех пользователей для рассылки"""
    async with async_session() as session:
        result = await session.execute(select(User.id))
        return result.scalars().all()


async def execute_raw_sql(sql_query: str):
    """Выполнение произвольного SQL (ОПАСНО, только для админа)"""
    async with async_session() as session:
        try:
            # Если это SELECT, возвращаем данные
            if sql_query.strip().upper().startswith("SELECT"):
                result = await session.execute(text(sql_query))
                return result.fetchall()
            else:
                # Если INSERT/UPDATE/DELETE/DROP
                await session.execute(text(sql_query))
                await session.commit()
                return "Запрос выполнен успешно (изменения сохранены)."
        except Exception as e:
            return f"Ошибка SQL: {e}"
