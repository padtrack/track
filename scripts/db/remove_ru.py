import asyncio

from sqlalchemy import select

from bot.utils import db


async def main():
    async with db.async_session() as session:
        users = (await session.execute(select(db.User).filter_by(wg_region="na"))).all()

        for (user,) in users:
            user.wg_region = None
            user.wg_id = None
            user.wg_ac = None

        guilds = (
            await session.execute(select(db.Guild).filter_by(wg_region="na"))
        ).all()

        for (guild,) in guilds:
            guild.wg_region = None

        print(f"{len(users)} users and {len(guilds)} guilds affected.")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())