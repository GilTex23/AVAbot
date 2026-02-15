from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import select, update, delete, and_
from database.models import Base, User, Subscription
import config

engine = create_async_engine(config.DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


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


async def update_user_voiceover(tg_id: int, vo: str):
    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.id == tg_id)
            .values(favorite_voiceover=vo)
        )
        await session.commit()


async def get_user_voiceover(tg_id: int):
    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == tg_id))
        return user.favorite_voiceover if user else "AniLiberty"


# --- SUBSCRIPTIONS ---
async def add_subscription(tg_id: int, title: str, url: str, last_ep: str, voiceover: str):
    """Добавляет подписку с конкретной озвучкой"""
    async with async_session() as session:
        # Проверяем уникальность по URL И ОЗВУЧКЕ
        # Человек может подписаться на одно аниме дважды с разной озвучкой
        existing = await session.scalar(
            select(Subscription).where(
                and_(
                    Subscription.user_id == tg_id,
                    Subscription.anime_url == url,
                    Subscription.voiceover == voiceover
                )
            )
        )
        if existing:
            return False

        session.add(Subscription(
            user_id=tg_id,
            anime_title=title,
            anime_url=url,
            last_episode=last_ep,
            voiceover=voiceover
        ))
        await session.commit()
        return True


async def get_all_subscriptions():
    async with async_session() as session:
        result = await session.execute(select(Subscription).join(User))
        return result.scalars().all()


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