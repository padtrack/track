from typing import Optional
import json
import os
import random

import difflib
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.track import Track
from bot.utils.logs import logger

GUILD_IDS = [
    552570749953507338,  # Bukis4Days
    611977431959732234,  # Bukis4Weekends
    641016852864040991,  # Bukis4Holidays
    677591786138632192,  # Bukis4TheGoodTimes
    758054424940773520,  # Bukis4TheBadTimes
    789203100308602920,  # Bukis4Ever
    908749316989022260,  # Bukis4TheRoad
]


_PASTAS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/public/buki_pastas.json"
)
with open(_PASTAS_PATH, "r") as fp:
    PASTAS = json.load(fp)


class BukiCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot
        self.emojis: Optional[dict] = None

        self.load_emojis.start()

    @tasks.loop(hours=1)
    async def load_emojis(self) -> None:
        logger.info("Loading Buki Emojis...")
        emojis = {}

        try:
            for guild_id in GUILD_IDS:
                guild = await self.bot.fetch_guild(guild_id)
                emojis.update(
                    {
                        emoji.name.lower(): emoji
                        for emoji in guild.emojis
                        if emoji.name.startswith("buki")
                    }
                )

            self.emojis = emojis
            logger.info("Buki Emojis Loaded")
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Failed to load Buki Emojis")

    @app_commands.command(
        name="buki",
        description="Returns a random queried emoji of (Fu)buki from KanColle.",
        extras={"category": "misc"},
    )
    async def buki(self, interaction: discord.Interaction, query: Optional[str] = None):
        if not self.emojis:
            await interaction.response.send_message("Emojis unavailable.")
        elif not query:
            await interaction.response.send_message(random.choice(list(self.emojis.values())))
            return

        query = query.lower()
        if not query.startswith("buki"):
            query = "buki" + query

        for name, emoji in self.emojis.items():
            if query == name:
                await interaction.response.send_message(emoji)
                return

        err_message = f"`{query}`? Could not find that Buki {self.emojis['bukitears']}"
        similar = difflib.get_close_matches(query, self.emojis.keys(), n=3, cutoff=0.75)
        if similar:
            err_message += "\nDid you mean...\n- " + "\n- ".join(similar)

        await interaction.response.send_message(err_message)

    @app_commands.command(
        name="pasta", description="Freshly cooked.", extras={"category": "misc"}
    )
    @app_commands.guilds(*GUILD_IDS)
    async def pasta(self, interaction: discord.Interaction, num: app_commands.Range[int, 1, len(PASTAS)]):
        await interaction.response.send_message(PASTAS[num - 1])


async def setup(bot: Track):
    await bot.add_cog(BukiCog(bot))
