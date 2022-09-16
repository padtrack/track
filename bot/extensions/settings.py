from discord.ext import commands
from discord import app_commands
import discord
from sqlalchemy import select

from bot.track import Track
from bot.utils import db, wows


wows_locale_choices = [
    app_commands.Choice(name=wows_locale, value=wows_locale)
    for wows_locale in list(dict.fromkeys(wows.DISCORD_TO_WOWS.values()))
]


class SettingsCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot: Track = bot

    @app_commands.command(
        name="setlanguage",
        description="Sets your preferred WoWS language.",
        extras={"category": "general"},
    )
    @app_commands.choices(wows_locale=wows_locale_choices)
    @app_commands.rename(wows_locale="language")
    async def set_user_language(
        self, interaction: discord.Interaction, wows_locale: str
    ):
        async with db.async_session() as session:
            user = (
                await session.execute(select(db.User).filter_by(id=interaction.user.id))
            ).scalar_one()

            user.wows_locale = wows_locale
            await session.commit()
        db.User.invalidate(id=interaction.user.id)

        await interaction.response.send_message(
            f"Language set to `{wows_locale}`.", ephemeral=True
        )

    @app_commands.command(
        name="setserverregion",
        description="Sets default WoWS region for this server.",
        extras={"category": "general"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_guild_region(
        self, interaction: discord.Interaction, region: wows.Regions
    ):
        async with db.async_session() as session:
            guild = (
                await session.execute(
                    select(db.Guild).filter_by(id=interaction.guild_id)
                )
            ).scalar_one()

            guild.wg_region = region
            await session.commit()
        db.Guild.invalidate(id=interaction.guild_id)

        await interaction.response.send_message(
            f"Server default region set to `{region}`."
        )


async def setup(bot: Track):
    await bot.add_cog(SettingsCog(bot))
