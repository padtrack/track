from __future__ import annotations
from typing import Optional, List, Tuple, TypeVar, Union
import dataclasses
import datetime

import aiohttp
import aiolimiter
import dacite
from discord.app_commands import Choice
from discord import app_commands
import discord

from bot.utils import db, wows, wg_api


URL_TEMPLATES = {
    "ru": "https://{}worldofwarships.ru",
    "eu": "https://{}worldofwarships.eu",
    "na": "https://{}worldofwarships.com",
    "asia": "https://{}worldofwarships.asia",
}
URLS: dict[str, str] = {key: value.format("") for key, value in URL_TEMPLATES.items()}
VORTEX: dict[str, str] = {
    key: value.format("vortex.") + "/api" for key, value in URL_TEMPLATES.items()
}
CLANS: dict[str, str] = {
    key: value.format("clans.") + "/api" for key, value in URL_TEMPLATES.items()
}
DEFAULT_BATTLE_TYPE = "pvp"
BATTLE_TYPES = {
    "pvp": {
        "default": 0,
        "sizes": {0: "pvp", 1: "pvp_solo", 2: "pvp_div2", 3: "pvp_div3"},
    },
    "pve": {"default": 0, "sizes": {0: "pve"}},
    "rank": {"default": 1, "sizes": {1: "rank_solo"}},
    "rank_old": {"default": 1, "sizes": {1: "rank_old_solo", 2: "rank_old_div2"}},
}

IT = TypeVar("IT", bound=datetime.datetime)
ST = TypeVar("ST", bound=datetime.datetime)
config = dacite.Config(
    type_hooks={
        IT: lambda x: datetime.datetime.fromtimestamp(x),
        ST: lambda x: datetime.datetime.fromisoformat(x),
    },
    check_types=False,
)
vortex_limit = aiolimiter.AsyncLimiter(10, 1)


@dataclasses.dataclass
class Player:
    region: str
    id: int
    name: str
    hidden_profile: bool
    clan_role: Optional[ClanRole]
    is_empty: bool

    @property
    def profile_url(self) -> str:
        url = URLS.get(self.region)
        return f"{url}/community/accounts/{self.id}-{self.name}"

    @property
    def wows_numbers_url(self) -> str:
        return f"https://{self.region}.wows-numbers.com/player/{self.id},{self.name}"


@dataclasses.dataclass
class ClanRole:
    clan: Clan
    clan_id: int
    joined_at: ST
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


@dataclasses.dataclass
class FullPlayer(Player):
    statistics: dict[str, dict[str, int]]

    activated_at: IT
    created_at: IT
    last_battle_time: IT

    karma: int
    leveling_points: int
    leveling_tier: int


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
            url = f"{VORTEX[region]}/accounts/{player_id}/"
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
    if hidden_profile:
        if clan_role:
            if statistics := await get_partial_statistics(
                region, player_id, clan_role.clan_id, battle_type=DEFAULT_BATTLE_TYPE
            ):
                stats, last_battle_time, online_status = statistics
                return PartialPlayer(
                    statistics={DEFAULT_BATTLE_TYPE: stats},
                    last_battle_time=last_battle_time,
                    online_status=online_status,
                    is_empty=False,
                    **kwargs,
                )

        return Player(is_empty=False, **kwargs)

    try:
        return dacite.from_dict(
            FullPlayer,
            {
                "statistics": {
                    index: data["statistics"][index]
                    for battle_type, type_data in BATTLE_TYPES.items()
                    for size, index in type_data["sizes"].items()
                },
                "activated_at": data["activated_at"],
                **data["statistics"]["basic"],
                "is_empty": False,
                **kwargs,
            },
            config=config,
        )
    except KeyError:
        return Player(
            is_empty=True,
            **kwargs,
        )


async def get_clan_role(
    region: str,
    player_id: Union[int, str],
) -> Optional[ClanRole]:
    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{VORTEX[region]}/accounts/{player_id}/clans"

            async with session.get(url) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                data = (await response.json())["data"]

    if "clan_id" in data and data["clan_id"] is None:
        return None
    else:
        return dacite.from_dict(ClanRole, data, config=config)


async def get_partial_statistics(
    region: str,
    player_id: Union[int, str],
    clan_id: Union[int, str],
    battle_type: str = DEFAULT_BATTLE_TYPE,
    season: Optional[int] = None,
) -> Optional[Tuple[PartialStatistics, datetime.datetime, bool]]:
    player_id = int(player_id)

    if season is None:
        season = wg_api.last_season[region]

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{CLANS[region]}/members/{clan_id}/"
            params = {"battle_type": battle_type}
            if season:
                params["season"] = season

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                items = (await response.json())["items"]

    for data in items:
        if data["id"] == player_id:
            return (
                dacite.from_dict(PartialStatistics, data, config),
                datetime.datetime.fromtimestamp(data["last_battle_time"]),
                data["online_status"],
            )

    return None


async def get_ship_statistics(
    region: str,
    player_id: Union[int, str],
    ship_id: Union[int, str],
    battle_type: str = DEFAULT_BATTLE_TYPE,
    access_code: Optional[
        str
    ] = None,
) -> Optional[dict[str, int]]:
    player_id = str(player_id)
    ship_id = str(ship_id)

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = (
                f"{VORTEX[region]}/accounts/{player_id}/ships/{ship_id}/{battle_type}/"
            )
            params = {"ac": access_code} if access_code else None

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError()

                data = (await response.json())["data"][player_id]

    if "hidden_profile" in data or not data["statistics"]:
        return None

    return data["statistics"][ship_id][battle_type]


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
            user = await db.User.get_or_create(id=interaction.user.id)
            if user.wg_region:
                return user.wg_region

        return wows.INFERRED_REGIONS.get(str(interaction.locale), "eu")

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[Choice[str]]:
        region = await self.get_region(interaction)

        async with vortex_limit:
            async with self.autocomplete_limit:
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
        region = await self.get_region(interaction)
        await interaction.response.defer()

        if player := await get_player(region, value):
            return player

        async with vortex_limit:
            async with aiohttp.ClientSession() as session:
                url = f"{VORTEX[region]}/accounts/search/{value}/?limit=1"

                async with session.get(url) as response:
                    if response.status != 200:
                        raise VortexError()

                    data = (await response.json())["data"]

        if not data:
            return None

        return await get_player(region, data[0]["spa_id"])
