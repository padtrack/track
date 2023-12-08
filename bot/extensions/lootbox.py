from typing import Any, Dict, List, Optional

import collections
import concurrent.futures
import dataclasses
import functools
import random

import aiohttp
import bs4
from discord.ext import commands, tasks
from discord import app_commands
import discord
import requests

from bot.track import Track
from bot.utils import errors
from bot.utils.logs import logger


QUERY = """
query {
    items {
        id
        title
        type {
            name
            title
        }
        restrictions {
            levels
        }
    }
    vehicles {
        id
        title
        level
        nation {
            name
            title
        }
        type {
            name
            title
        }
    }
    currencies {
        name
        title
    }
    crews {
        id
        title
        nation {
            name
            title
        }
    }
    collectibleAlbum {
        id
        title
        name
    }
}
"""


executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
box_names, obj_data = {}, {}


def scrape():
    global box_names, obj_data
    try:
        response = requests.get(
            "https://worldofwarships.com/en/content/contents-and-drop-rates-of-containers/",
            headers={"x-requested-with": "XMLHttpRequest"},
        )

        if response.status_code != 200:
            logger.error(f"Error code {response.status_code} while fetching boxes")
            return

        soup = bs4.BeautifulSoup(response.text, "html.parser")
        box_names = {
            tag["box-id"]: {
                "name": tag["preview-title"],
                "clean": LootboxTransformer.clean(tag["preview-title"]),
            }
            for tag in soup.find_all(lambda t: t.has_attr("box-id"))
        }

        response = requests.post(
            "https://vortex.worldofwarships.com/api/graphql/glossary/",
            json=[{"query": QUERY, "variables": {"languageCode": "en"}}],
        )

        if response.status_code != 200:
            logger.error(
                f"Error code {response.status_code} while fetching box rewards"
            )
            return

        temp = {}

        for category, objects in response.json()[0]["data"].items():
            for obj in objects:
                obj["category"] = category

                if category == "currencies":
                    temp[obj["name"]] = obj
                else:
                    temp[obj["id"]] = obj

        temp["wows_premium"] = {
            "name": "wows_premium",
            "title": "WoWS Premium Days",
            "category": "currencies",
        }

        obj_data = temp

        return True
    except Exception as e:
        logger.warning("Unhandled exception while loading Lootboxes", exc_info=e)
        return


class LootboxTransformer(app_commands.Transformer):
    MIN_AC_LENGTH = 2
    MAX_AC_RESULTS = 10

    @staticmethod
    def clean(string: str) -> str:
        return string.replace('"', "").replace(" ", "").lower()

    async def autocomplete(
        self, interaction: discord.Interaction, value: str
    ) -> List[app_commands.Choice[str]]:
        clean = self.clean(value)
        results = []

        if len(clean) < self.MIN_AC_LENGTH:
            return results

        for box_id, data in box_names.items():
            if clean in data["clean"]:
                results.append(app_commands.Choice(name=data["name"], value=box_id))

            if len(results) == self.MAX_AC_RESULTS:
                break

        return results

    async def transform(self, interaction: discord.Interaction, value: str) -> str:
        if value not in box_names:
            raise errors.CustomError("Select a lootbox type from autocomplete results.")

        return value


@dataclasses.dataclass
class Slot:
    choices: List[Dict[str, Any]]
    weights: List[int]
    index: collections.Counter[str]
    pity: int = 0

    @functools.cached_property
    def threshold(self) -> Optional[int]:
        for choice in self.choices:
            value = choice.get("savePoint", None)
            if value:
                return value

        return None


@dataclasses.dataclass(frozen=True)
class WoWSObject:
    identifier: Any
    crew_level: Optional[int] = None
    ship_id: Optional[int] = None

    def __str__(self):
        obj = obj_data[str(self.identifier)]
        title = obj["title"]

        match obj["category"]:
            case "currencies":
                return title
            case "items":
                if self.ship_id:
                    return f"{title} ({obj['type']['title']} for {obj_data[str(self.ship_id)]['title']})"
                else:
                    base = f"{title} ({obj['type']['title']})"
                    try:
                        if obj["type"]["name"] == "multiboost":
                            return f"T{obj['restrictions']['levels'][0]} {base}"
                        else:
                            return base
                    except (AttributeError, KeyError, IndexError):
                        return base
            case "collectibleAlbum":
                return f'"{title}" collection'
            case "crews":
                return f"{title} [{self.crew_level} pts]"
            case "vehicles":
                return (
                    f"{title} "
                    f"[T{obj['level']} {obj['nation']['title']} {obj['type']['title']}, "
                    f"{self.crew_level} pts]"
                )
            case _:
                return self.identifier


class LootboxCog(commands.Cog):
    def __init__(self, bot: Track):
        self.bot = bot

        self.box_names = {}
        self.data = {}
        self.task_scrape.start()

    @tasks.loop(hours=1)
    async def task_scrape(self):
        logger.info("Loading Lootboxes...")
        result = await self.bot.loop.run_in_executor(executor, scrape)

        if not result:
            logger.warning("Failed to load Lootboxes")
        else:
            logger.info("Lootboxes loaded")

    @app_commands.command(
        name="lootbox",
        description="Simulates rolling lootboxes.",
        extras={"category": "wows"},
    )
    async def lootbox(
        self,
        interaction: discord.Interaction,
        lootbox: app_commands.Transform[str, LootboxTransformer],
        quantity: app_commands.Range[int, 1, 50] = 1,
    ):
        await interaction.response.defer()

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://vortex.worldofwarships.com/api/get_lootbox/en/{lootbox}/"
            ) as response:
                data = (await response.json())["data"]
                global_threshold: Optional[int] = data.get("savePoint", None)

                slots = []
                for slot in data["slots"]:
                    choices, weights = [], []

                    for info in slot["commonRewards"].values():
                        for reward in info["rewards"]:
                            choices.append(reward)
                            weights.append(reward["weight"])

                    for bucket, info in slot["valuableRewards"].items():
                        info["bucket"] = bucket
                        random.shuffle(info["rewards"])
                        choices.append(info)
                        weights.append(info["weight"])

                    slots.append(Slot(choices, weights, collections.Counter()))

                results = collections.Counter()
                used_pity = 0

                def add_result(obj_id, extras, value):
                    results[
                        WoWSObject(
                            obj_id,
                            crew_level=extras.get("crewLevel", None),
                            ship_id=extras["id"]
                            if extras["type"] == "ship"
                            else extras.get("shipId", None),
                        )
                    ] += value

                for _ in range(quantity):
                    for slot in slots:
                        if (
                            slot.threshold is not None
                            and slot.pity == slot.threshold - 1
                        ) or (
                            global_threshold is not None
                            and slot.pity == global_threshold - 1
                        ):
                            used_pity += 1
                            result = next(c for c in slot.choices if "savePoint" in c)
                        else:
                            result = random.choices(slot.choices, slot.weights)[0]

                        unique = result.get("hasUniqueRewards", None)
                        if unique is None:  # common
                            identifier = (
                                result["type"] if result["id"] is None else result["id"]
                            )
                            add_result(identifier, result, result["amount"])
                        else:  # valuable
                            if not unique:
                                reward = random.choice(result["rewards"])
                                add_result(reward["id"], reward, reward["amount"])
                            else:
                                if slot.index[result["bucket"]] >= len(
                                    result["rewards"]
                                ):  # all unique rewards awarded
                                    if (
                                        result["rerollNonUniqueCrews"]
                                        and result["rewards"][0]["type"] == "crew"
                                    ):
                                        reward = random.choice(result["rewards"])
                                        add_result(
                                            reward["id"], reward, reward["amount"]
                                        )
                                    else:
                                        identifier = (
                                            data["filler"]["type"]
                                            if data["filler"]["id"] is None
                                            else data["filler"]["id"]
                                        )
                                        add_result(
                                            identifier,
                                            data["filler"],
                                            data["filler"]["amount"],
                                        )
                                else:
                                    reward = result["rewards"][
                                        slot.index[result["bucket"]]
                                    ]
                                    add_result(reward["id"], reward, reward["amount"])
                                    slot.index[result["bucket"]] += 1

                        if "savePoint" in result:
                            slot.pity = 0
                        else:
                            slot.pity += 1

                embed = discord.Embed(
                    title="Lootbox Results",
                    description=f"{data['title']}\nQuantity: `{quantity}`\n",
                )
                embed.set_footer(text=f"Pity Used: {used_pity}")

                categories = {
                    cat: []
                    for cat in [
                        "currencies",
                        "items",
                        "collectibleAlbum",
                        "crews",
                        "vehicles",
                    ]
                }
                for obj, amount in results.most_common():
                    category = obj_data[str(obj.identifier)]["category"]
                    categories[category].append((str(obj), amount))

                for category, pairs in categories.items():
                    if pairs:
                        pretty = (
                            "Collections"
                            if category == "collectibleAlbum"
                            else category.title()
                        )
                        if len(pairs) < 20:
                            embed.add_field(
                                name=pretty,
                                value="\n".join(
                                    "- "
                                    + label
                                    + (f": `{amount}`" if amount > 1 else "")
                                    for label, amount in pairs
                                ),
                                inline=False,
                            )
                        else:
                            embed.add_field(
                                name=pretty,
                                value=" 𝅹 𝅹 • 𝅹 𝅹 ".join(  # invisible characters (U+1D179) here
                                    label + (f": `{amount}`" if amount > 1 else "")
                                    for label, amount in pairs
                                ),
                                inline=False,
                            )

                try:
                    await interaction.followup.send(embed=embed)
                except discord.HTTPException:
                    await interaction.followup.send("Result too long for Discord.")


async def setup(bot: Track):
    await bot.add_cog(LootboxCog(bot))
