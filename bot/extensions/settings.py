from typing import Dict, List, Optional
import json

from discord.ext import commands
from discord import app_commands
import discord
from sqlalchemy import select

from bot.track import Track
from bot.utils import db, wows


CATEGORIES = [
    "wows",
    "fun",
]
COMMANDS = [
    "profile",
    "build",
    "clan",
    "myclan",
    "dualrender",
    "guess",
    "inspect",
    "link",
    "render",
    "stats",
    "mystats",
    "update",
    "aah",
    "buki",
    "pog",
]


disable_choices = [
    app_commands.Choice(name=target, value=target) for target in CATEGORIES + COMMANDS
]
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
    @app_commands.describe(wows_locale="Your preferred language.")
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
    @app_commands.describe(region="The region to set as the default in this server.")
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

            guild.wg_region = region.value
            await session.commit()
        db.Guild.invalidate(id=interaction.guild_id)

        await interaction.response.send_message(
            f"Server default region set to `{region.value}`."
        )

    @staticmethod
    def format_structure(structure: Dict[str, List[int]]):
        string = ""

        for name, targets in structure.items():
            string += (
                f"**{name}** (category)\n" if name in CATEGORIES else f"**/{name}**\n"
            )
            string += "".join(
                f"- {'`global`' if not target else f'<#{target}>'}\n"
                for target in targets
            )
            string += "\n"

        return string

    @app_commands.command(
        name="toggle",
        description="Manage disabled commands and categories for this server.",
        extras={"category": "general"},
    )
    @app_commands.describe(
        target="A command of category from this bot",
        channel="The channel to apply this to.",
    )
    @app_commands.choices(target=disable_choices)
    @app_commands.rename(target="command_or_category")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(
        self,
        interaction: discord.Interaction,
        target: Optional[str],
        channel: Optional[discord.TextChannel],
    ):
        async with db.async_session() as session:
            guild = (
                await session.execute(
                    select(db.Guild).filter_by(id=interaction.guild_id)
                )
            ).scalar_one()

            data = json.loads(guild.disabled)

            if not target:
                if not data:
                    await interaction.response.send_message(
                        "Everything is enabled.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"Disabled commands/categories:\n{self.format_structure(data)}",
                        ephemeral=True,
                    )
                return

            target_channel = 0 if not channel else channel.id
            channel_message = (
                "globally" if not target_channel else f"in {channel.mention}"
            )

            if target not in data:
                data[target] = [target_channel]
                message = f"`{target}` disabled {channel_message}."
            elif target_channel not in data[target]:
                data[target].append(target_channel)
                message = f"`{target}` disabled {channel_message}."
            else:
                data[target].remove(target_channel)
                if not data[target]:
                    del data[target]

                message = f"`{target}` enabled {channel_message}."

            guild.disabled = json.dumps(data)
            await session.commit()
        db.Guild.invalidate(id=interaction.guild_id)

        await interaction.response.send_message(
            f"{message}. New structure:\n{self.format_structure(data)}"
        )


async def setup(bot: Track):
    await bot.add_cog(SettingsCog(bot))
