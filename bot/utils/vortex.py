from __future__ import annotations
from typing import Optional, List, Tuple, Union
import dataclasses
import datetime

import aiohttp
import aiolimiter
from discord.app_commands import Choice
from discord import app_commands
import discord

from bot.utils import db, wows, wg_api

URLS = {
    "ru": "https://worldofwarships.ru",
    "eu": "https://worldofwarships.eu",
    "na": "https://worldofwarships.com",
    "asia": "https://worldofwarships.asia",
}
VORTEX = {
    "ru": "https://vortex.worldofwarships.ru/api/",
    "eu": "https://vortex.worldofwarships.eu/api/",
    "na": "https://vortex.worldofwarships.com/api/",
    "asia": "https://vortex.worldofwarships.asia/api/",
}
CLANS = {
    "ru": "https://clans.worldofwarships.ru/api/",
    "eu": "https://clans.worldofwarships.eu/api/",
    "na": "https://clans.worldofwarships.com/api/",
    "asia": "https://clans.worldofwarships.asia/api/",
}
BATTLE_TYPES = [
    "pvp",
    "pve",
    "rank_solo",
    "rank_old_solo",
    "cvc",
]

vortex_limit = aiolimiter.AsyncLimiter(10, 1)


@dataclasses.dataclass
class Player:
    region: str
    id: int
    name: str
    hidden_profile: bool
    clan_role: Optional[ClanRole]

    @property
    def profile_link(self) -> str:
        url = URLS.get(self.region)
        return f"{url}/community/accounts/{self.id}-{self.name}"


@dataclasses.dataclass
class ClanRole:
    clan: Clan
    clan_id: int
    joined_at: datetime.datetime
    role: str


@dataclasses.dataclass
class Clan:
    color: int
    name: str
    members_count: int
    tag: str


@dataclasses.dataclass
class PartialStatistics:
    battles_count: int
    battles_per_day: float

    damage_per_battle: float
    frags_per_battle: float
    exp_per_battle: float
    wins_percentage: float


@dataclasses.dataclass
class PartialPlayer(Player):
    statistics: dict[str, PartialStatistics]
    last_battle_time: datetime.datetime
    online_status: bool  # this doesn't seem to actually work without auth


class VortexError(Exception):
    # TODO: log these!
    pass


async def get_player(
    region: str,
    player_id: Union[int, str],
    access_code: Optional[str] = None,
) -> Optional[Player]:
    player_id = str(player_id)

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{VORTEX[region]}accounts/{player_id}/"
            params = {"ac": access_code} if access_code else None

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                data = (await response.json())["data"][player_id]

                hidden_profile = "hidden_profile" in data
                clan_role = await get_clan_role(region, player_id)
                kwargs = {
                    "region": region,
                    "id": int(player_id),
                    "name": data["name"],
                    "hidden_profile": hidden_profile,
                    "clan_role": clan_role,
                }
                if hidden_profile and clan_role:
                    if statistics := await get_partial_statistics(
                        region, player_id, clan_role.clan_id, battle_type="pvp"
                    ):
                        stats, last_battle_time, online_status = statistics
                        return PartialPlayer(
                            statistics={"pvp": stats},
                            last_battle_time=last_battle_time,
                            online_status=online_status,
                            **kwargs,
                        )

                return Player(**kwargs)


async def get_clan_role(
    region: str,
    player_id: Union[int, str],
) -> Optional[ClanRole]:
    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{VORTEX[region]}accounts/{player_id}/clans"

            async with session.get(url) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                data = (await response.json())["data"]

                return ClanRole(
                    clan=Clan(**data["clan"]),
                    role=data["role"],
                    joined_at=datetime.datetime.fromisoformat(data["joined_at"]),
                    clan_id=data["clan_id"],
                )


async def get_partial_statistics(
    region: str,
    player_id: Union[int, str],
    clan_id: Union[int, str],
    battle_type: str = None,
    season: Optional[int] = None,
) -> Optional[Tuple[PartialStatistics, datetime.datetime, bool]]:
    player_id = int(player_id)

    if season is None:
        season = wg_api.last_season[region]

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{CLANS[region]}members/{clan_id}/"
            params = {"battle_type": battle_type if battle_type else "pvp"}
            if season:
                params["season"] = season

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                for data in (await response.json())["items"]:
                    if data["id"] == player_id:
                        return (
                            PartialStatistics(
                                battles_count=data["battles_count"],
                                battles_per_day=data["battles_per_day"],
                                damage_per_battle=data["damage_per_battle"],
                                frags_per_battle=data["frags_per_battle"],
                                exp_per_battle=data["exp_per_battle"],
                                wins_percentage=data["wins_percentage"],
                            ),
                            datetime.datetime.fromtimestamp(data["last_battle_time"]),
                            data["online_status"],
                        )

                return None


class PlayerTransformer(app_commands.Transformer):
    autocomplete_limit = aiolimiter.AsyncLimiter(5, 1)

    @staticmethod
    async def get_region(interaction: discord.Interaction) -> str:
        if (
            hasattr(interaction.namespace, "region")
            and interaction.namespace.region is not None
        ):
            return interaction.namespace.region
        else:
            user = await db.User.get(id=interaction.user.id)
            if user.wg_region:
                return user.wg_region

        return wows.INFERRED_REGIONS.get(str(interaction.locale), "eu")

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[Choice[str]]:
        region = self.get_region(interaction)

        async with vortex_limit:
            async with self.autocomplete_limit:
                async with aiohttp.ClientSession() as session:
                    url = f"{VORTEX[region]}accounts/search/autocomplete/{value}/"
                    async with session.get(url) as response:
                        if response.status != 200:
                            return []

                        return [
                            app_commands.Choice(
                                name=result["name"], value=str(result["spa_id"])
                            )
                            for result in (await response.json())["data"]
                        ]

    async def transform(
        self, interaction: discord.Interaction, value: str
    ) -> Optional[Player]:
        region = await self.get_region(interaction)
        await interaction.response.defer()

        if player := await get_player(region, value):
            return player

        async with vortex_limit:
            async with aiohttp.ClientSession() as session:
                url = f"{VORTEX[region]}accounts/search/{value}/?limit=1"

                async with session.get(url) as response:
                    if response.status != 200:
                        raise VortexError()

                    if not (results := (await response.json())["data"]):
                        return None
                    else:
                        return await get_player(region, results[0]["spa_id"])
