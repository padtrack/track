from __future__ import annotations

import aiohttp

from config import cfg


API = {
    "ru": "https://api.worldofwarships.ru/wows/",
    "eu": "https://api.worldofwarships.eu/wows/",
    "na": "https://api.worldofwarships.com/wows/",
    "asia": "https://api.worldofwarships.asia/wows/",
}


seasons = {}
last_season = {}


async def get_seasons():
    data, last = {}, {}

    async with aiohttp.ClientSession() as session:
        for region, api in API.items():
            url = f"{api}clans/season/"

            async with session.get(
                url, params={"application_id": cfg.wg.app_id}
            ) as response:
                if response.status != 200:
                    return None

                data[region] = (await response.json())["data"]
                last[region] = max(
                    int(season_num)
                    for season_num in data[region].keys()
                    if len(season_num) < 3
                )

    global seasons, last_season
    seasons = data
    last_season = last
