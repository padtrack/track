from typing import Dict, List, Tuple
import os
import toml

from discord.ext import commands
from discord import app_commands, ui
import discord

from bot.track import Track
from bot.utils import wows


DOCUMENT_URL = (
    "https://docs.google.com/document/d/1XfsIIbyORQAxgOE-ao_nVSP8_fpa1igg0t48pXZFIu0/"
    "#bookmark={}"
)
BUILDS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/public/builds.toml"
)


class BuildsEmbed(discord.Embed):
    def __init__(self, builds: List[Tuple[str, Dict]], **kwargs):
        super().__init__(
            title=f"Found {len(builds)} " f"build{'s' if len(builds) > 1 else ''}!",
            description="Document: [wo.ws/builds](https://wo.ws/builds)",
            **kwargs,
        )


class BuildsView(ui.View):
    def __init__(self, builds: List[Tuple[str, Dict]], **kwargs):
        super().__init__(**kwargs)

        for name, build in builds:
            self.add_item(ui.Button(label=name, url=DOCUMENT_URL.format(build["id"])))


class BuildsCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot
        with open(BUILDS_PATH) as fp:
            self.builds = toml.load(fp)

    @app_commands.command(name="build")
    async def build(
        self,
        interaction: discord.Interaction,
        ship: app_commands.Transform[wows.Ship, wows.ShipTransformer],
    ):
        results = [
            (name, build)
            for name, build in self.builds.items()
            if ship.index in build["ships"]
        ]
        if not results:
            await interaction.response.send_message(
                f"No builds found for {ship.tl(interaction)['full']}."
            )
        else:
            await interaction.response.send_message(
                embed=BuildsEmbed(results), view=BuildsView(results)
            )


async def setup(bot: Track):
    await bot.add_cog(BuildsCog(bot))
