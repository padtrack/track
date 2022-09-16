from typing import Optional

from discord.ext import commands
from discord import app_commands
import discord


from bot.track import Track
from bot.utils import db


HELP_MESSAGE = """
The wiki page for the bot is available at <https://github.com/padtrack/track/wiki>.
For a commands reference, see <https://github.com/padtrack/track/wiki/Commands>.
If you're looking to invite the bot, use `/invite`.
If you're looking for help with WoWS gameplay, join Help Me <https://discord.gg/c4vK9rM>

If you have further questions, or would like to follow development, you can join the support server:
https://discord.gg/dU39sjq
"""


class UserDataEmbed(discord.Embed):
    def __init__(self, user_profile: db.User):
        super().__init__(title="User Profile")

        self.add_field(
            name="Guess",
            value=f"Guessed: {user_profile.guess_count}\n"
            f"Record: {user_profile.guess_record}",
        )


class GeneralCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

        self.permissions = discord.Permissions(412317248576)
        self.bot.remove_command("help")

    @app_commands.command(
        name="profile",
        description="Fetch profile for you or a specified user.",
        extras={"category": "general"},
    )
    @app_commands.describe(user="The user to fetch a profile for.")
    async def user_data(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ):
        if not user:
            user = interaction.user

        result = await db.User.get(id=user.id)

        if not result:
            await interaction.response.send_message("No profile found for this user.")
            return

        await interaction.response.send_message(embed=UserDataEmbed(result[0][0]))

    @app_commands.command(
        name="invite",
        description="Gives you a link to invite this bot.",
        extras={"category": "general"},
    )
    async def invite(self, interaction: discord.Interaction):
        url = discord.utils.oauth_url(self.bot.user.id, permissions=self.permissions)
        await interaction.response.send_message(
            f"You can invite me by opening my profile, or by using this url:\n{url}",
            ephemeral=True,
        )

    @app_commands.command(
        name="help",
        description="Shows information about this bot.",
        extras={"category": "general"},
    )
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)


async def setup(bot: Track):
    await bot.add_cog(GeneralCog(bot))
