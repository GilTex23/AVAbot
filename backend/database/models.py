from sqlalchemy import BigInteger, Boolean, String, Column, ForeignKey, Integer, DateTime, Date, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
import datetime


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)  # Telegram ID
    username = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    favorite_voiceover = Column(String, default="AniLiberty")
    quiet_hours_enabled = Column(Boolean, nullable=False, default=False)
    quiet_hours_start = Column(String, nullable=False, default="23:00")
    quiet_hours_end = Column(String, nullable=False, default="09:00")
    # Часовой пояс пользователя (исторически назван по тихим часам): расписание, прогнозы и тихие часы
    quiet_timezone = Column(String, nullable=False, default="Europe/Moscow")
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    anime_url = Column(String, nullable=False)
    anime_title = Column(String, nullable=False)
    poster_url = Column(String, nullable=True)
    voiceover = Column(String, nullable=False, default="Unknown")

    total_episodes = Column(Integer, nullable=True)

    last_episode = Column(String, nullable=True)
    # Когда в подписке последний раз появлялась новая серия (UTC); нужно для чистки брошенных озвучек
    last_episode_at = Column(DateTime, nullable=True, default=datetime.datetime.utcnow)
    # Когда последний раз смотрели страницу тайтла (UTC); при подписке она только что загружена
    info_checked_at = Column(DateTime, nullable=True, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="subscriptions")


class ScraperApiKey(Base):
    __tablename__ = 'scraper_api_keys'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    key_encrypted = Column(String, nullable=False)  # Fernet, секрет в SCRAPER_KEYS_SECRET
    enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="active")  # active / low / exhausted / invalid

    # Данные из https://api.scraperapi.com/account
    request_count = Column(Integer, nullable=True)
    request_limit = Column(Integer, nullable=True)
    failed_request_count = Column(Integer, nullable=True)
    subscription_date = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)

    last_used_at = Column(DateTime, nullable=True)
    last_error = Column(String, nullable=True)
    last_error_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EpisodeRelease(Base):
    """Серия в озвучке из ленты на главной AnimeGO — история для прогноза следующей серии"""
    __tablename__ = 'episode_releases'
    __table_args__ = (UniqueConstraint('anime_url', 'studio', 'episode', name='uq_episode_releases_anime_studio_episode'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    anime_url = Column(String, nullable=False, index=True)
    anime_title = Column(String, nullable=False)
    studio = Column(String, nullable=False)
    episode = Column(Integer, nullable=False)
    released_at = Column(DateTime, nullable=False)  # UTC; из ленты, а если время не распознано — момент, когда увидели
    first_seen_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class EpisodeAiring(Base):
    """Выход серии в Японии по расписанию на главной AnimeGO"""
    __tablename__ = 'episode_airings'

    anime_url = Column(String, primary_key=True)
    episode = Column(Integer, primary_key=True)
    air_at = Column(DateTime, nullable=False)  # UTC
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)


class DailyStat(Base):
    """
    Дневные счётчики для статистики в админке: metric — что считаем, dimension — разрез
    (например, metric='scraper.success', dimension='checker:home'). Хранятся 180 дней.
    """
    __tablename__ = 'daily_stats'

    day = Column(Date, primary_key=True)
    metric = Column(String, primary_key=True)
    dimension = Column(String, primary_key=True, default="")
    value = Column(BigInteger, nullable=False, default=0)


class UserActivity(Base):
    """Пользователь заходил в этот день (source: miniapp / bot) — для активных за день и неделю"""
    __tablename__ = 'user_activity'

    day = Column(Date, primary_key=True)
    user_id = Column(BigInteger, primary_key=True)
    source = Column(String, primary_key=True)


class ScraperKeySnapshot(Base):
    """Счётчики ключа из /account на момент опроса (раз в 6 часов) — остаток кредитов во времени"""
    __tablename__ = 'scraper_key_snapshots'
    __table_args__ = (Index('ix_scraper_key_snapshots_taken_at', 'taken_at'),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    taken_at = Column(DateTime, nullable=False)
    key_id = Column(Integer, ForeignKey('scraper_api_keys.id', ondelete='SET NULL'), nullable=True)
    key_name = Column(String, nullable=False)
    request_count = Column(Integer, nullable=True)
    request_limit = Column(Integer, nullable=True)
    status = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False)


class ScraperApiKeyUsage(Base):
    __tablename__ = 'scraper_api_key_usage'

    key_id = Column(Integer, ForeignKey('scraper_api_keys.id', ondelete='CASCADE'), primary_key=True)
    day = Column(Date, primary_key=True)
    success = Column(Integer, nullable=False, default=0)
    failed = Column(Integer, nullable=False, default=0)
