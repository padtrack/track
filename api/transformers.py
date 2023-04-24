from typing import List, Optional

__all__ = [
    "PlayerTransformer",
    "ClanTransformer",
    "get_region",
]

import aiohttp
import aiolimiter
from discord import app_commands
import discord

from bot.utils import db, wows
from .models import Player, FullClan
from .urls import VORTEX, CLANS_API
from .vortex import get_player, get_clan, vortex_limit, VortexError


autocomplete_limit = aiolimiter.AsyncLimiter(5, 1)


async def get_region(interaction: discord.Interaction) -> str:
    if (
        hasattr(interaction.namespace, "region")
        and interaction.namespace.region is not None
    ):
        return interaction.namespace.region

    user = await db.User.get_or_create(id=interaction.user.id)
    if user.wg_region:
        return user.wg_region

    guild = await db.Guild.get_or_create(id=interaction.guild_id)
    if guild.wg_region:
        return guild.wg_region

    return wows.INFERRED_REGIONS.get(str(interaction.locale), "eu")


class PlayerTransformer(app_commands.Transformer):
    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[app_commands.Choice[str]]:
        await interaction.response.defer()
        region = await get_region(interaction)

        async with vortex_limit:
            async with autocomplete_limit:
                async with aiohttp.ClientSession() as session:
                    url = f"{VORTEX[region]}/accounts/search/autocomplete/{value}/"

                    async with session.get(url) as response:
                        if response.status != 200:
                            return []

                        data = (await response.json())["data"]

        return [
            app_commands.Choice(name=result["name"], value=str(result["spa_id"]))
            for result in data
        ]

    async def transform(
        self, interaction: discord.Interaction, value: str
    ) -> Optional[Player]:
        await interaction.response.defer()
        region = await get_region(interaction)
        user = await db.User.get_or_create(id=interaction.user.id)
        access_code = user.wg_ac

        if player := await get_player(region, value, access_code):
            return player

        async with vortex_limit:
            async with aiohttp.ClientSession() as session:
                url = f"{VORTEX[region]}/accounts/search/{value}/?limit=1"

                async with session.get(url) as response:
                    if response.status != 200:
                        raise VortexError(response.status)

                    data = (await response.json())["data"]

        if not data:
            return None

        return await get_player(region, data[0]["spa_id"], access_code)


class ClanTransformer(app_commands.Transformer):
    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[app_commands.Choice[str]]:
        await interaction.response.defer()
        region = await get_region(interaction)

        async with vortex_limit:
            async with autocomplete_limit:
                async with aiohttp.ClientSession() as session:
                    url = f"{CLANS_API[region]}/search/autocomplete/"
                    params = {"type": "clans", "search": value}

                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            return []

                        result = (await response.json())["search_autocomplete_result"]

        return [
            app_commands.Choice(
                name=f"[{clan['tag']}] {clan['name']}", value=str(clan["id"])
            )
            for clan in result
        ]

    async def transform(
        self, interaction: discord.Interaction, value: str
    ) -> Optional[FullClan]:
        await interaction.response.defer()
        region = await get_region(interaction)

        if clan := await get_clan(region, value):
            return clan

        async with vortex_limit:
            async with aiohttp.ClientSession() as session:
                url = f"{CLANS_API[region]}/search/clans/"
                params = {
                    "battle_type": "pvp",
                    "offset": 0,
                    "limit": 1,
                    "search": value,
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        raise VortexError(response.status)

                    clans = (await response.json())["clans"]

        if not clans:
            return None

        return await get_clan(region, clans[0]["id"])
