from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select, update, delete, and_, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import joinedload
from database.models import (
    Base, User, Subscription, AnimeTitle, Voiceover, ScraperApiKey, ScraperApiKeyUsage, EpisodeRelease, EpisodeAiring,
    DailyStat, UserActivity, ScraperKeySnapshot,
)
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
            session.add(User(id=tg_id, username=username))
            await session.commit()
            return True
        return False


async def upsert_user_profile(tg_id: int, username: str | None = None, photo_url: str | None = None):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        if not user:
            user = User(id=tg_id, username=username, photo_url=photo_url)
            session.add(user)
        else:
            if username is not None:
                user.username = username
            if photo_url is not None:
                user.photo_url = photo_url

        await session.commit()
        await session.refresh(user)
        return user


async def update_user_favorite_voiceovers(tg_id: int, voiceovers: list[str]):
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == tg_id)
            .values(favorite_voiceovers=voiceovers)
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


async def update_user_timezone(tg_id: int, timezone: str):
    async with async_session() as session:
        await session.execute(update(User).where(User.id == tg_id).values(quiet_timezone=timezone))
        await session.commit()


async def get_user_favorite_voiceovers(tg_id: int) -> list[str]:
    async with async_session() as session:
        favorites = await session.scalar(select(User.favorite_voiceovers).where(User.id == tg_id))
        return list(favorites or [])


# --- ANIME TITLES ---
async def upsert_anime_titles(rows: list[dict]):
    """rows: id, url, title, poster_url. Название и адрес обновляются, постер — только если пришёл новый"""
    rows = list({row["id"]: row for row in rows}.values())
    if not rows:
        return
    now = datetime.datetime.utcnow()
    async with async_session() as session:
        stmt = pg_insert(AnimeTitle).values([{**row, "updated_at": now} for row in rows])
        stmt = stmt.on_conflict_do_update(
            index_elements=[AnimeTitle.id],
            set_={
                "url": stmt.excluded.url,
                "title": stmt.excluded.title,
                "poster_url": func.coalesce(stmt.excluded.poster_url, AnimeTitle.poster_url),
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await session.execute(stmt)
        await session.commit()


async def get_anime_title(anime_id: int):
    async with async_session() as session:
        return await session.get(AnimeTitle, anime_id)


# --- VOICEOVERS ---
async def touch_voiceovers(names: list[str], seen_at: datetime.datetime | None = None):
    """Добавляет новые озвучки в справочник и обновляет время, когда озвучку видели последний раз"""
    names = sorted(set(names))
    if not names:
        return
    seen_at = seen_at or datetime.datetime.utcnow()
    async with async_session() as session:
        stmt = pg_insert(Voiceover).values([{"name": name, "first_seen_at": seen_at, "last_seen_at": seen_at} for name in names])
        stmt = stmt.on_conflict_do_update(
            index_elements=[Voiceover.name],
            set_={"last_seen_at": func.greatest(Voiceover.last_seen_at, stmt.excluded.last_seen_at)},
        )
        await session.execute(stmt)
        await session.commit()


async def get_voiceover_catalog(releases_since: datetime.datetime):
    """Справочник с популярностью: серий в ленте с releases_since и подписок; популярные первыми"""
    releases = (
        select(EpisodeRelease.studio.label("name"), func.count().label("releases"))
        .where(EpisodeRelease.released_at >= releases_since)
        .group_by(EpisodeRelease.studio)
        .subquery()
    )
    subscriptions = (
        select(Subscription.voiceover.label("name"), func.count().label("subscriptions"))
        .group_by(Subscription.voiceover)
        .subquery()
    )
    release_count = func.coalesce(releases.c.releases, 0)
    subscription_count = func.coalesce(subscriptions.c.subscriptions, 0)
    async with async_session() as session:
        result = await session.execute(
            select(Voiceover.id, Voiceover.name, Voiceover.last_seen_at, release_count, subscription_count)
            .outerjoin(releases, releases.c.name == Voiceover.name)
            .outerjoin(subscriptions, subscriptions.c.name == Voiceover.name)
            .order_by(release_count.desc(), subscription_count.desc(), func.lower(Voiceover.name))
        )
        return [
            {"id": id_, "name": name, "last_seen_at": last_seen_at, "releases": releases_, "subscriptions": subscriptions_}
            for id_, name, last_seen_at, releases_, subscriptions_ in result.all()
        ]


async def get_voiceover_names(names: list[str]) -> set[str]:
    """Какие из названий есть в справочнике"""
    if not names:
        return set()
    async with async_session() as session:
        return set(await session.scalars(select(Voiceover.name).where(Voiceover.name.in_(names))))


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


async def get_recent_releases(since: datetime.datetime):
    """Серии, которые бот видел в ленте начиная с since — из них досылаются уведомления"""
    async with async_session() as session:
        result = await session.execute(select(EpisodeRelease).where(EpisodeRelease.first_seen_at >= since))
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


# --- STATISTICS (админка) ---
async def increment_daily_stats(rows: list[tuple[str, str, int]], day: datetime.date | None = None):
    """rows: (metric, dimension, value) — прибавляются к счётчикам за день"""
    totals = {}
    for metric, dimension, value in rows:
        totals[(metric, dimension)] = totals.get((metric, dimension), 0) + value
    if not totals:
        return
    day = day or datetime.datetime.utcnow().date()
    async with async_session() as session:
        stmt = pg_insert(DailyStat).values([
            {"day": day, "metric": metric, "dimension": dimension, "value": value}
            for (metric, dimension), value in totals.items()
        ])
        stmt = stmt.on_conflict_do_update(
            index_elements=[DailyStat.day, DailyStat.metric, DailyStat.dimension],
            set_={"value": DailyStat.value + stmt.excluded.value},
        )
        await session.execute(stmt)
        await session.commit()


async def record_user_activity(user_id: int, source: str, day: datetime.date | None = None):
    async with async_session() as session:
        stmt = pg_insert(UserActivity).values(day=day or datetime.datetime.utcnow().date(), user_id=user_id, source=source)
        await session.execute(stmt.on_conflict_do_nothing())
        await session.commit()


async def add_key_snapshots(rows: list[dict]):
    if not rows:
        return
    async with async_session() as session:
        await session.execute(pg_insert(ScraperKeySnapshot).values(rows))
        await session.commit()


async def get_daily_stats(since: datetime.date):
    async with async_session() as session:
        result = await session.execute(
            select(DailyStat.day, DailyStat.metric, DailyStat.dimension, DailyStat.value).where(DailyStat.day >= since)
        )
        return result.all()


async def get_key_usage_by_day(since: datetime.date):
    """(day, key name, success, failed) по ключам, которые ещё есть в базе"""
    async with async_session() as session:
        result = await session.execute(
            select(ScraperApiKeyUsage.day, ScraperApiKey.name, ScraperApiKeyUsage.success, ScraperApiKeyUsage.failed)
            .join(ScraperApiKey, ScraperApiKey.id == ScraperApiKeyUsage.key_id)
            .where(ScraperApiKeyUsage.day >= since)
        )
        return result.all()


async def get_key_snapshots(since: datetime.datetime):
    async with async_session() as session:
        result = await session.execute(
            select(ScraperKeySnapshot).where(ScraperKeySnapshot.taken_at >= since).order_by(ScraperKeySnapshot.taken_at)
        )
        return result.scalars().all()


async def get_activity_by_day(since: datetime.date):
    """(day, source, число пользователей) и отдельно — все уникальные за день"""
    async with async_session() as session:
        by_source = await session.execute(
            select(UserActivity.day, UserActivity.source, func.count(func.distinct(UserActivity.user_id)))
            .where(UserActivity.day >= since)
            .group_by(UserActivity.day, UserActivity.source)
        )
        total = await session.execute(
            select(UserActivity.day, func.count(func.distinct(UserActivity.user_id)))
            .where(UserActivity.day >= since)
            .group_by(UserActivity.day)
        )
        return by_source.all(), total.all()


async def count_active_users(since: datetime.date) -> int:
    async with async_session() as session:
        return await session.scalar(
            select(func.count(func.distinct(UserActivity.user_id))).where(UserActivity.day >= since)
        )


async def get_new_users_by_day(since: datetime.date):
    async with async_session() as session:
        day = func.date(User.registered_at)
        result = await session.execute(
            select(day, func.count(User.id))
            .where(User.registered_at >= datetime.datetime.combine(since, datetime.time()))
            .group_by(day)
        )
        return result.all()


async def get_bot_overview(top: int = 10):
    """Итоги по пользователям и подпискам для статистики"""
    async with async_session() as session:
        users = await session.scalar(select(func.count(User.id)))
        subscriptions = await session.scalar(select(func.count(Subscription.id)))
        subscribers = await session.scalar(select(func.count(func.distinct(Subscription.user_id))))
        quiet = await session.scalar(select(func.count(User.id)).where(User.quiet_hours_enabled.is_(True)))
        top_titles = await session.execute(
            select(Subscription.anime_title, func.count(Subscription.id).label("count"))
            .group_by(Subscription.anime_title)
            .order_by(text("count DESC"), Subscription.anime_title)
            .limit(top)
        )
        voiceovers = await session.execute(
            select(Subscription.voiceover, func.count(Subscription.id).label("count"))
            .group_by(Subscription.voiceover)
            .order_by(text("count DESC"), Subscription.voiceover)
            .limit(top)
        )
        return {
            "users": users,
            "subscriptions": subscriptions,
            "subscribers": subscribers,
            "quiet_hours_users": quiet,
            "top_titles": [{"title": title, "count": count} for title, count in top_titles.all()],
            "voiceovers": [{"name": name, "count": count} for name, count in voiceovers.all()],
        }


async def get_history_overview(since: datetime.date):
    async with async_session() as session:
        releases = await session.scalar(select(func.count(EpisodeRelease.id)))
        airings = await session.scalar(select(func.count()).select_from(EpisodeAiring))
        titles = await session.scalar(select(func.count(func.distinct(EpisodeRelease.anime_url))))
        day = func.date(EpisodeRelease.first_seen_at)
        per_day = await session.execute(
            select(day, func.count(EpisodeRelease.id))
            .where(EpisodeRelease.first_seen_at >= datetime.datetime.combine(since, datetime.time()))
            .group_by(day)
        )
        return {"releases": releases, "airings": airings, "titles": titles, "per_day": per_day.all()}


async def get_database_overview():
    """Размер базы и таблиц — средствами самого Postgres"""
    async with async_session() as session:
        size = await session.scalar(text("SELECT pg_database_size(current_database())"))
        tables = await session.execute(text(
            "SELECT relname, n_live_tup, pg_total_relation_size(relid), pg_relation_size(relid), pg_indexes_size(relid) "
            "FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC"
        ))
        connections = await session.scalar(text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        ))
        version = await session.scalar(text("SHOW server_version"))
        started_at = await session.scalar(text("SELECT pg_postmaster_start_time()"))
        return {
            "size_bytes": size,
            "tables": [
                {"name": name, "rows": rows, "total_bytes": total, "table_bytes": table, "index_bytes": indexes}
                for name, rows, total, table, indexes in tables.all()
            ],
            "connections": connections,
            "version": version,
            "started_at": started_at,
        }


async def prune_statistics(before: datetime.date) -> dict:
    """Удаляет статистику и историю старше before; возвращает, сколько строк удалено по таблицам"""
    before_dt = datetime.datetime.combine(before, datetime.time())
    statements = {
        "daily_stats": delete(DailyStat).where(DailyStat.day < before),
        "user_activity": delete(UserActivity).where(UserActivity.day < before),
        "scraper_api_key_usage": delete(ScraperApiKeyUsage).where(ScraperApiKeyUsage.day < before),
        "scraper_key_snapshots": delete(ScraperKeySnapshot).where(ScraperKeySnapshot.taken_at < before_dt),
        "episode_releases": delete(EpisodeRelease).where(EpisodeRelease.first_seen_at < before_dt),
        "episode_airings": delete(EpisodeAiring).where(EpisodeAiring.air_at < before_dt),
    }
    deleted = {}
    async with async_session() as session:
        for table, statement in statements.items():
            deleted[table] = (await session.execute(statement)).rowcount
        await session.commit()
    return deleted


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
