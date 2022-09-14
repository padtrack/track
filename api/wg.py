from __future__ import annotations
__all__ = [
    "seasons", "get_seasons", "buildings", "get_buildings"
]

from typing import Dict

import aiohttp

import dacite

from config import cfg
from .models import *
from .utils import *


API = {
    "ru": "https://api.worldofwarships.ru/wows",
    "eu": "https://api.worldofwarships.eu/wows",
    "na": "https://api.worldofwarships.com/wows",
    "asia": "https://api.worldofwarships.asia/wows",
}
PARAMS = {"application_id": cfg.wg.app_id, "language": "en"}


seasons: Dict[str, SeasonsData] = {}
buildings: Dict[str, BuildingsData] = {}


class WGAPIError(APIError):
    pass


async def get_seasons():
    temp = {}

    async with aiohttp.ClientSession() as session:
        for region, api in API.items():
            url = f"{api}/clans/season/"

            async with session.get(
                url, params=PARAMS
            ) as response:
                if response.status != 200:
                    raise WGAPIError(response.status)

                data = (await response.json())
                temp[region] = dacite.from_dict(SeasonsData, data, config)

    global seasons
    seasons = temp


async def get_buildings():
    temp = {}

    async with aiohttp.ClientSession() as session:
        for region, api in API.items():
            url = f"{api}/clans/glossary/"

            async with session.get(
                url=url, params=PARAMS
            ) as response:
                if response.status != 200:
                    raise WGAPIError(response.status)

                data = (await response.json())["data"]
                temp[region] = dacite.from_dict(BuildingsData, data, config)

    global buildings
    buildings = temp
