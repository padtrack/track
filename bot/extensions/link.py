from __future__ import annotations
from typing import Optional
import re

from discord.ext import commands
from discord import app_commands, ui
import discord
from sqlalchemy import select

import api
from bot.track import Track
from bot.utils import db


URLS = {
    "ru": "https://worldofwarships.ru/en/community/accounts/",
    "eu": "https://worldofwarships.eu/en/community/accounts/",
    "na": "https://worldofwarships.com/en/community/accounts/",
    "asia": "https://worldofwarships.asia/en/community/accounts/",
}


class LinkModal(ui.Modal):
    PATTERN = re.compile(r"(\d+)-[a-zA-Z0-9_]+/([a-zA-Z0-9-_]+)")

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

                    player = await api.get_player(region, player_id)

                    if not player:
                        await interaction.followup.send(
                            "Invalid profile URL.\n", ephemeral=True
                        )
                        return
                    elif not player.hidden_profile:
                        await interaction.followup.send(
                            "Profile is not on the correct visibility setting.\n"
                            'Please ensure that it is still on the "Via Link" setting '
                            "and that you have saved your changes by refreshing the page.\n"
                            "Changes can sometimes take up to a few minutes to be reflected WG server-side.\n",
                            ephemeral=True,
                        )
                        return

                    player = await api.get_player(region, player_id, access_code)

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
    INFO_URL = "https://github.com/padtrack/track/wiki/Links"

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
        await interaction.response.send_message(
            "Click your region's link below to visit your profile. "
            "You may need to log in if you haven't already.\n"
            + "\n".join(f"<{url}>" for url in URLS.values())
            + "\n\n"
            'After you have done so, set your profile privacy to "Via Link".\n'
            "Paste the profile link into the Modal prompted by pressing the button.\n"
            "After you have successfully linked, you may change your profile visibility.\n",
            view=view,
            ephemeral=True,
        )
        view.message = await interaction.original_response()


async def setup(bot: Track):
    await bot.add_cog(LinkCog(bot))
