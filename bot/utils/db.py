import os

import cachetools
import cachetools.keys
from sqlalchemy import Boolean, Column, Integer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# _DB_PATH = ":memory:"
_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/private/bot.db"
)
engine = create_async_engine(f"sqlite+aiosqlite:///{_DB_PATH}", future=True)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


class CachedMixin:
    CACHE_SIZE = 1000
    cache = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.cache = cachetools.LRUCache(maxsize=cls.CACHE_SIZE)

    @classmethod
    def invalidate(cls, **kwargs):
        try:
            del cls.cache[cachetools.keys.hashkey(**kwargs)]
        except KeyError:
            pass

    @classmethod
    async def get(cls, **kwargs):
        key = cachetools.keys.hashkey(**kwargs)
        if (cached := cls.cache.get(key)) is not None:
            return cached

        # noinspection PyUnresolvedReferences
        clauses = [cls.__table__.columns[key] == value for key, value in kwargs.items()]

        async with async_session() as session:
            statement = select(cls).where(*clauses)
            result = (await session.execute(statement)).all()
            cls.cache[key] = result
            return result

    @classmethod
    async def get_or_create(cls, **kwargs):
        if result := await cls.get(**kwargs):
            return result[0][0]
        else:
            async with async_session() as session:
                # noinspection PyArgumentList
                obj = cls(**kwargs)
                session.add(obj)
                await session.commit()
            cls.invalidate(**kwargs)
            return obj


class User(Base, CachedMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    is_blacklisted = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)


class Guild(Base, CachedMixin):
    __tablename__ = "guilds"

    id = Column(Integer, primary_key=True)
    is_blacklisted = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)


if __name__ == "__main__":

    async def create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    import asyncio

    asyncio.run(create_tables())
