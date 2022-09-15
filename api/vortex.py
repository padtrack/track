from __future__ import annotations

__all__ = [
    "DEFAULT_BATTLE_TYPE",
    "BATTLE_TYPES",
    "vortex_limit",
    "VortexError",
    "get_player",
    "get_ship_statistics",
    "get_partial_statistics",
    "get_clan_members",
    "get_clan",
    "get_ladder_position",
]

from typing import List, Optional, Union

import aiohttp
import aiolimiter
import dacite

from .models import *
from .urls import CLANS_API, VORTEX
from .utils import *
from . import wg

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
REALMS = {
    "ru": "ru", "eu": "eu", "na": "us", "asia": "sg"
}

vortex_limit = aiolimiter.AsyncLimiter(10, 1)


class VortexError(APIError):
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
                    raise VortexError(response.status)

                data = (await response.json())["data"][player_id]

    hidden_profile = "hidden_profile" in data
    clan_role = await get_clan_role(region, player_id)
    kwargs = {
        "region": region,
        "id": int(player_id),
        "name": data["name"],
        "hidden_profile": hidden_profile,
        "clan_role": clan_role,
        "used_access_code": access_code,
    }
    if hidden_profile:
        if clan_role:
            if statistics := await get_partial_statistics(
                region, player_id, clan_role.clan_id
            ):
                return PartialPlayer(
                    statistics={DEFAULT_BATTLE_TYPE: statistics},
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
                **data["statistics"]["basic"],
                "activated_at": data["activated_at"],
                "is_empty": False,
                **kwargs,
            },
            config,
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
                    raise VortexError(response.status)

                data = (await response.json())["data"]

    if "clan_id" in data and data["clan_id"] is None:
        return None
    else:
        return dacite.from_dict(ClanRole, data, config)


async def get_ship_statistics(
    region: str,
    player_id: Union[int, str],
    ship_id: Union[int, str],
    battle_type: str = DEFAULT_BATTLE_TYPE,
    access_code: Optional[str] = None,
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
                    raise VortexError(response.status)

                data = (await response.json())["data"][player_id]

    if "hidden_profile" in data or not data["statistics"]:
        return None

    return data["statistics"][ship_id][battle_type]


async def get_partial_statistics(
    region: str,
    player_id: Union[int, str],
    clan_id: Union[int, str],
    battle_type: str = DEFAULT_BATTLE_TYPE,
) -> Optional[ClanMemberStatistics]:
    player_id = int(player_id)

    if not (members := await get_clan_members(region, clan_id, battle_type)):
        return None

    for member in members:
        if member.id == player_id:
            return member

    return None


async def get_clan_members(
    region: str,
    clan_id: Union[int, str],
    battle_type: str = DEFAULT_BATTLE_TYPE,
    season: Optional[int] = None,
) -> Optional[List[ClanMemberStatistics]]:
    if season is None:
        season = wg.seasons[region].last_clan_season

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{CLANS_API[region]}/members/{clan_id}/"
            params = {"battle_type": battle_type, "season": season}

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError(response.status)

                items = (await response.json())["items"]

    return [dacite.from_dict(ClanMemberStatistics, data, config) for data in items]


async def get_clan(region: str, clan_id: Union[int, str]):
    try:
        clan_id = int(clan_id)
    except ValueError:
        return None

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{CLANS_API[region]}/clanbase/{clan_id}/claninfo/"

            async with session.get(url) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError(response.status)

                view = (await response.json())["clanview"]

    if not view["wows_ladder"]:  # TODO: check behavior when CB season ends
        view["wows_ladder"] = None

    view["region"] = region
    return dacite.from_dict(FullClan, view, config)


async def get_ladder_position(region: str, clan_id: Union[str, int], local: bool, season: Optional[int] = None) -> Optional[LadderPosition]:
    if season is None:
        season = wg.seasons[region].last_clan_season

    realm = REALMS[region] if local else "global"

    async with vortex_limit:
        async with aiohttp.ClientSession() as session:
            url = f"{CLANS_API[region]}/ladder/structure/"
            params = {"clan_id": clan_id, "season": season, "realm": realm}

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    return None
                elif response.status != 200:
                    raise VortexError(response.status)

                segment = await response.json()

    for data in segment:
        if data["id"] == clan_id:
            return dacite.from_dict(LadderPosition, data, config)

    return None
