from __future__ import annotations
from typing import Optional
import re

from discord.ext import commands
from discord import app_commands, ui
import discord
from sqlalchemy import select

from bot.track import Track
from bot.utils import db, vortex


URLS = {
    "ru": "https://profile.worldofwarships.ru",
    "eu": "https://profile.worldofwarships.eu",
    "na": "https://profile.worldofwarships.com",
    "asia": "https://profile.worldofwarships.asia",
}


class LinkModal(ui.Modal):
    PATTERN = re.compile(r"/statistics/(\d+)/ac/([a-zA-Z0-9-_]+)/")

    def __init__(self):
        super().__init__(
            title="Link Account",
        )

        self.link = ui.TextInput(
            label="Profile Link",
            style=discord.TextStyle.short,
            placeholder="Paste your link here!",
            required=True,
        )
        self.add_item(self.link)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.link.value

        for region, url in URLS.items():
            if value.startswith(url):
                value = value[len(url) :]
                match = re.match(self.PATTERN, value)

                if match:
                    await interaction.response.defer()
                    player_id, access_code = int(match.group(1)), match.group(2)

                    player = await vortex.get_player(region, player_id)

                    if not player:
                        await interaction.followup.send(
                            "Invalid profile URL.\n", ephemeral=True
                        )
                        return
                    elif not player.hidden_profile:
                        await interaction.followup.send(
                            "Profile is not on the correct visibility setting.\n"
                            'Please ensure that it is still on the "Via Link" setting '
                            'and that you have pressed the "Save" button when you submit the URL.',
                            ephemeral=True,
                        )
                        return

                    player = await vortex.get_player(region, player_id, access_code)

                    if not player:
                        await interaction.followup.send(
                            "Invalid profile URL.\n", ephemeral=True
                        )
                        return
                    elif player.hidden_profile:
                        await interaction.followup.send(
                            "Invalid access code.\n"
                            "Please ensure that you have not generated a new code before submitting the URL.",
                            ephemeral=True,
                        )
                        return

                    async with db.async_session() as session:
                        user = (
                            await session.execute(
                                select(db.User).filter_by(id=interaction.user.id)
                            )
                        ).scalar_one()

                        user.wg_region = region
                        user.wg_id = player_id
                        user.wg_ac = access_code
                        await session.commit()
                    db.User.invalidate(id=interaction.user.id)

                    await interaction.followup.send(
                        "Link successful!\n"
                        "You may now change your profile visibility to public if you wish.",
                        ephemeral=True,
                    )
                    return

        await interaction.response.send_message(
            "This seems to be an incomplete URL. "
            "Please ensure that you have copied the complete link!",
            ephemeral=True,
        )


class LinkButton(ui.Button):
    def __init__(self):
        super().__init__(
            label="Submit",
            style=discord.ButtonStyle.success,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LinkModal())


class LinkView(ui.View):
    # TODO: change to main branch
    INFO_URL = "https://github.com/padtrack/track/blob/rewrite/docs/LINKS.md"

    def __init__(self):
        super().__init__(timeout=300)

        self.message: Optional[discord.Message] = None
        self.link_button = LinkButton()

        self.add_item(self.link_button)
        self.add_item(ui.Button(label="More Info", url=self.INFO_URL))

    async def on_timeout(self):
        self.link_button.disabled = True

        await self.message.edit(view=self)


class LinkCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

    @app_commands.command(
        name="link",
        description="Link your WG account to your Discord account.",
        extras={"category": "wows"},
    )
    async def link(self, interaction: discord.Interaction):
        view = LinkView()
        # TODO: remove disclaimer on release
        await interaction.response.send_message(
            "**DISCLAIMER: THIS IS A TEST VERSION OF THE BOT. THE DATABASE MAY BE WIPED IN BETWEEN TESTS.**"
            "Click your region's link below to visit your profile. "
            "You may need to log in if you haven't already.\n"
            + "\n".join(URLS.values())
            + "\n\n"
            'After you have done so, set your profile privacy to "Via Link" in the Summary tab.\n'
            "Paste the profile link into the Modal prompted by pressing the button.",
            view=view,
        )
        view.message = await interaction.original_response()


async def setup(bot: Track):
    await bot.add_cog(LinkCog(bot))
