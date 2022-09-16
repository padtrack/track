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

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        else:
            logger.error(
                f"Ignoring exception in command {ctx.command.name}", exc_info=error
            )


async def setup(bot: Track):
    await bot.add_cog(Core(bot))
