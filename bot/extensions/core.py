import logging

from discord.ext import commands

from bot.track import Track

logger = logging.getLogger("track")


class Core(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logger.log(logging.INFO, f"Logged in as {self.bot.user}")

    @commands.Cog.listener()
    async def on_disconnect(self):
        logger.log(logging.INFO, "Disconnected")

    @commands.Cog.listener()
    async def on_resumed(self):
        logger.log(logging.INFO, "Reconnected")


async def setup(bot: Track):
    await bot.add_cog(Core(bot))
