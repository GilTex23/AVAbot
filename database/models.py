from sqlalchemy import BigInteger, String, Column, ForeignKey, Integer, DateTime
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs
import datetime


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'

    id = Column(BigInteger, primary_key=True)  # Telegram ID
    username = Column(String, nullable=True)
    favorite_voiceover = Column(String, default="AniLiberty")
    registered_at = Column(DateTime, default=datetime.datetime.utcnow)

    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")


class Subscription(Base):
    __tablename__ = 'subscriptions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'))
    anime_url = Column(String, nullable=False)
    anime_title = Column(String, nullable=False)
    voiceover = Column(String, nullable=False, default="Unknown")

    total_episodes = Column(Integer, nullable=True)

    last_episode = Column(String, nullable=True)

    user = relationship("User", back_populates="subscriptions")