from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select, update, delete, and_, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import joinedload
from database.models import Base, User, Subscription, ScraperApiKey, ScraperApiKeyUsage, EpisodeRelease, EpisodeAiring
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
async def add_subscription(
    tg_id: int,
    title: str,
    url: str,
    last_ep: str,
    voiceover: str,
    total_eps: int = None,
    poster_url: str | None = None,
):
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
            poster_url=poster_url,
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


async def mark_anime_info_checked(url: str):
    """Отмечает, что страницу тайтла только что проверили (для всех подписок на него)"""
    async with async_session() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.anime_url == url)
            .values(info_checked_at=datetime.datetime.utcnow())
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
            .values(last_episode=episode, last_episode_at=datetime.datetime.utcnow())
        )
        await session.commit()


# --- EPISODE HISTORY (прогноз следующей серии) ---
async def record_episode_releases(rows: list[dict]):
    """rows: anime_url, anime_title, studio, episode, released_at. Уже известные серии не перезаписываются"""
    if not rows:
        return
    now = datetime.datetime.utcnow()
    async with async_session() as session:
        stmt = pg_insert(EpisodeRelease).values([{**row, "first_seen_at": now} for row in rows])
        await session.execute(stmt.on_conflict_do_nothing(constraint="uq_episode_releases_anime_studio_episode"))
        await session.commit()


async def record_episode_airings(rows: list[dict]):
    """rows: anime_url, episode, air_at. Время выхода обновляется, если расписание сдвинули"""
    if not rows:
        return
    now = datetime.datetime.utcnow()
    async with async_session() as session:
        stmt = pg_insert(EpisodeAiring).values([{**row, "updated_at": now} for row in rows])
        stmt = stmt.on_conflict_do_update(
            index_elements=[EpisodeAiring.anime_url, EpisodeAiring.episode],
            set_={"air_at": stmt.excluded.air_at, "updated_at": stmt.excluded.updated_at},
        )
        await session.execute(stmt)
        await session.commit()


async def fill_total_episodes(url: str, total_eps: int):
    """Проставляет число серий подпискам на тайтл, у которых оно ещё неизвестно"""
    async with async_session() as session:
        await session.execute(
            update(Subscription)
            .where(Subscription.anime_url == url, Subscription.total_episodes.is_(None))
            .values(total_episodes=total_eps)
        )
        await session.commit()


async def get_episode_releases(urls: set[str]):
    async with async_session() as session:
        result = await session.execute(select(EpisodeRelease).where(EpisodeRelease.anime_url.in_(urls)))
        return result.scalars().all()


async def get_episode_airings(urls: set[str]):
    async with async_session() as session:
        result = await session.execute(select(EpisodeAiring).where(EpisodeAiring.anime_url.in_(urls)))
        return result.scalars().all()


async def get_release_lag_samples(since: datetime.datetime):
    """(studio, released_at, air_at) по всем тайтлам — типичная задержка каждой студии"""
    async with async_session() as session:
        result = await session.execute(
            select(EpisodeRelease.studio, EpisodeRelease.released_at, EpisodeAiring.air_at)
            .join(
                EpisodeAiring,
                and_(
                    EpisodeAiring.anime_url == EpisodeRelease.anime_url,
                    EpisodeAiring.episode == EpisodeRelease.episode,
                ),
            )
            .where(EpisodeRelease.released_at >= since)
        )
        return result.all()


# --- SCRAPER API KEYS ---
async def get_scraper_keys():
    async with async_session() as session:
        result = await session.execute(select(ScraperApiKey).order_by(ScraperApiKey.id))
        return result.scalars().all()


async def get_scraper_key(key_id: int):
    async with async_session() as session:
        return await session.scalar(select(ScraperApiKey).where(ScraperApiKey.id == key_id))


async def count_scraper_keys() -> int:
    async with async_session() as session:
        return await session.scalar(select(func.count(ScraperApiKey.id)))


async def add_scraper_key(name: str, email: str | None, key_encrypted: str, **values):
    async with async_session() as session:
        key = ScraperApiKey(name=name, email=email, key_encrypted=key_encrypted, **values)
        session.add(key)
        await session.commit()
        await session.refresh(key)
        return key


async def update_scraper_key(key_id: int, **values):
    async with async_session() as session:
        await session.execute(update(ScraperApiKey).where(ScraperApiKey.id == key_id).values(**values))
        await session.commit()


async def delete_scraper_key(key_id: int):
    async with async_session() as session:
        await session.execute(delete(ScraperApiKey).where(ScraperApiKey.id == key_id))
        await session.commit()


async def record_scraper_key_usage(key_id: int, success: bool, error: str | None = None):
    """Считает запрос в дневной статистике ключа и обновляет его счётчики"""
    now = datetime.datetime.utcnow()
    async with async_session() as session:
        stmt = pg_insert(ScraperApiKeyUsage).values(
            key_id=key_id, day=now.date(), success=int(success), failed=int(not success)
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ScraperApiKeyUsage.key_id, ScraperApiKeyUsage.day],
            set_={
                "success": ScraperApiKeyUsage.success + stmt.excluded.success,
                "failed": ScraperApiKeyUsage.failed + stmt.excluded.failed,
            },
        )
        await session.execute(stmt)

        if success:
            values = {"request_count": func.coalesce(ScraperApiKey.request_count, 0) + 1, "last_used_at": now}
        else:
            values = {"last_error": (error or "Unknown error")[:500], "last_error_at": now}
        await session.execute(update(ScraperApiKey).where(ScraperApiKey.id == key_id).values(**values))
        await session.commit()


async def get_scraper_usage(since: datetime.date):
    """Суммарные запросы по всем ключам за каждый день начиная с since"""
    async with async_session() as session:
        result = await session.execute(
            select(
                ScraperApiKeyUsage.day,
                func.sum(ScraperApiKeyUsage.success),
                func.sum(ScraperApiKeyUsage.failed),
            )
            .where(ScraperApiKeyUsage.day >= since)
            .group_by(ScraperApiKeyUsage.day)
            .order_by(ScraperApiKeyUsage.day)
        )
        return result.all()


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
