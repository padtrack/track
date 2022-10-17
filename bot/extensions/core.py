from typing import Union
import collections
import datetime
import os
import pickle

from discord.ext import commands, tasks
from discord import app_commands
import discord

from bot.track import Track
from bot.utils.logs import logger
from config import cfg


STATS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/private/stats.pickle"
)
CREATED = datetime.datetime.fromtimestamp(cfg.created, datetime.timezone.utc)


class Core(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.session = collections.Counter()

        try:
            with open(STATS_PATH, "rb") as fp:
                self.persistent = pickle.load(fp)
        except FileNotFoundError:
            self.persistent = collections.Counter()

        self.save_stats.start()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f"Logged in as {self.bot.user}")

    @commands.Cog.listener()
    async def on_disconnect(self):
        logger.info("Disconnected")

    @commands.Cog.listener()
    async def on_resumed(self):
        logger.info("Reconnected")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.NotOwner):
            logger.warning("Ignored non-owner user")
            return
        else:
            logger.error(
                f"Ignoring exception in command {ctx.command.name}", exc_info=error
            )

    @tasks.loop(minutes=1)
    async def save_stats(self):
        with open(STATS_PATH, "wb") as fp:
            pickle.dump(self.persistent, fp)

    @commands.Cog.listener()
    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: Union[app_commands.Command, app_commands.ContextMenu],
    ):
        self.session["commands"] += 1
        self.session[command.name] += 1
        self.persistent["commands"] += 1
        self.persistent[command.name] += 1

    @app_commands.command(
        name="status",
        description="View information about the bot.",
        extras={"category": "general"},
    )
    async def status(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"Online since: {discord.utils.format_dt(self.bot.online_since, style='R')}\n"
            f"Servers: `{len(self.bot.guilds)}`\n"
            f"Commands (session): `{self.session['commands']}`\n"
            f"Commands (since {discord.utils.format_dt(CREATED, 'd')}): `{self.persistent['commands']}`\n\n"
            "Popular commands:\n"
            + "\n".join(
                f"- {name}: `{count}`"
                for name, count in self.persistent.most_common(5)[1:]
            ),
            ephemeral=True,
        )


async def setup(bot: Track):
    await bot.add_cog(Core(bot))
