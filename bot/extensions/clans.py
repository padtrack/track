from discord.ext import commands, tasks
from discord import app_commands
import discord

import api
from bot.track import Track
from bot.utils.logs import logger


# TODO: truncate description, clean markdown
class ClanEmbed(discord.Embed):
    DEFAULT_COLOR = 0xFFFFFF
    PROGRESS_FOREGROUND = "▰"
    PROGRESS_BACKGROUND = "▱"

    def __init__(self, clan: api.FullClan):
        color = self.DEFAULT_COLOR if not clan.wows_ladder else clan.wows_ladder.color

        super().__init__(
            title=f"[{clan.clan.tag}] {clan.clan.name}",
            description=f"Created: <t:{int(clan.clan.created_at.timestamp())}:D>\n"
            f"Achievements: `{len(clan.achievements)}`",
            color=color,
        )

        all_modifiers = set()
        strings = []
        for building in clan.buildings.values():
            all_modifiers.update(building.modifiers)

            building_id = building.modifiers[0]
            building_type = api.wg.buildings[clan.region].type_of(building_id)
            total = api.wg.buildings[clan.region].upgrades_count(building_type)
            remaining = total - building.level
            name = building.name.replace("_", " ").title()  # TODO: look for real building names

            if building.level:
                strings.append(
                    f"{name} "
                    f"{self.PROGRESS_FOREGROUND * building.level}"
                    f"{self.PROGRESS_BACKGROUND * remaining}"
                )

        oil_remaining = 0
        for building in api.wg.buildings[clan.region].buildings.values():
            if building.building_id not in all_modifiers:
                oil_remaining += building.cost

        self.add_field(name="Base", value=f"Oil remaining to max: `{oil_remaining}`\n" + "\n".join(strings))


class ClansCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.load_seasons.start()

    @tasks.loop(hours=1)
    async def load_seasons(self):
        logger.info("Loading Buildings...")

        try:
            await api.wg.get_buildings()
            logger.info("Buildings Loaded")
        except Exception as e:
            logger.warning("Failed to load Buildings", exc_info=e)

            if not api.wg.buildings:
                import sys

                sys.exit(1)

    @app_commands.command()
    async def clan(
        self,
        interaction: discord.Interaction,
        clan: app_commands.Transform[api.FullClan, api.ClanTransformer],
    ):
        if clan is None:
            await interaction.followup.send("No clans found.")
            return

        await interaction.followup.send(embed=ClanEmbed(clan))


async def setup(bot: Track):
    await bot.add_cog(ClansCog(bot))
