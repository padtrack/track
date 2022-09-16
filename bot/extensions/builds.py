from typing import List, Tuple
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
    def __init__(self, builds: List[Tuple[str, str, int]], **kwargs):
        super().__init__(
            title=f"Found {len(builds)} " f"build{'s' if len(builds) > 1 else ''}!",
            description="Document: [wo.ws/builds](https://wo.ws/builds)",
            **kwargs,
        )


class BuildsView(ui.View):
    def __init__(self, builds: List[Tuple[str, str, int]], **kwargs):
        super().__init__(**kwargs)

        for count, (bookmark_id, name, ships_length) in enumerate(builds):
            row = count if len(builds) <= 5 else None

            self.add_item(
                ui.Button(label=name, url=DOCUMENT_URL.format(bookmark_id), row=row)
            )


class BuildsCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot
        with open(BUILDS_PATH) as fp:
            data = toml.load(fp)
            self.builds = {
                k: v for k, v in sorted(data.items(), key=lambda i: len(i[1]["ships"]))
            }

    @app_commands.command(
        name="build",
        description="Shortcut for the builds in wo.ws/builds",
        extras={"category": "wows"},
    )
    @app_commands.describe(ship="The ship to use.")
    async def build(
        self,
        interaction: discord.Interaction,
        ship: app_commands.Transform[wows.Ship, wows.ShipTransformer],
    ):
        results = [
            (bookmark_id, build["name"], len(build["ships"]))
            for bookmark_id, build in self.builds.items()
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
