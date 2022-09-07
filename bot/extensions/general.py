from typing import Optional

from discord.ext import commands
from discord import app_commands
import discord


from bot.track import Track
from bot.utils import db


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
        self.bot = bot

    @app_commands.command(
        name="profile",
        description="Fetch profile for you or a specified user.",
        extras={"category": "general"},
    )
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


async def setup(bot: Track):
    await bot.add_cog(GeneralCog(bot))
