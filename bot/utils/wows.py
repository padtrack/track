from __future__ import annotations

import dataclasses
import json
import os
from typing import List

import discord
from discord import app_commands, Interaction
from discord.app_commands import Choice

from bot.utils import errors

DISCORD_TO_WOWS = {
    "en-US": "en",
    "en-GB": "en",
    "zh-CN": "zh",
    "zh-TW": "zh_tw",
    "cs": "cs",
    "nl": "nl",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "ja": "ja",
    "ko": "ko",
    "pl": "pl",
    "pt-BR": "pt_br",
    "ru": "ru",
    "es-ES": "es",
    "th": "th",
    "tr": "tr",
    "uk": "uk",
}
GROUPS = [
    "start",  # Tier 1
    "demoWithStats",  # Public test
    "demoWithoutStats",  # Closed test
    "special",  # Premium
    "specialUnsellable",  # Unsellable premiums (Flint, Missouri, etc.)
    "ultimate",  # Tier 10 reward ships
    "upgradeable",  # Tech-tree ships
    "upgradeableExclusive",  # Other Free EXP ships (Nelson, Alaska, etc.)
    "upgradeableUltimate",  # Free EXP Tier 10 reward ships (Smaland, Hayate, etc.)
    "legendaryBattle",  # Superships
]
_CHARS_TABLE = {" ": "", "-": "", ".": "", "'": ""}

_SHIPS_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/public/ships.json"
)


@dataclasses.dataclass
class Ship:
    id: int
    index: str
    isPaperShip: bool
    group: str
    level: int
    name: str
    species: str
    nation: str
    translations: dict[str, dict[str, str]]

    @staticmethod
    def clean(string: str):
        return string.lower().translate(_CHARS_TABLE)

    def tl(self, interaction: discord.Interaction):
        wows_locale = DISCORD_TO_WOWS.get(interaction.locale, "en")
        return self.translations[wows_locale]


def get_ships():
    with open(_SHIPS_DATA_PATH, encoding="utf-8") as fp:
        ships_data = json.load(fp)

    _ships = {
        data["index"]: Ship(**data) for data in ships_data if data["group"] in GROUPS
    }

    for ship in _ships.values():
        for tl in ship.translations.values():
            tl["clean_short"] = ship.clean(tl["short"])
            tl["clean_full"] = ship.clean(tl["full"])

    return _ships


ships: dict[str, Ship] = get_ships()


class ShipTransformer(app_commands.Transformer):
    MIN_AC_LENGTH = 2
    MAX_AC_RESULTS = 10
    CUTOFF = 5

    async def autocomplete(
        self, interaction: Interaction, value: str
    ) -> List[Choice[str]]:
        clean = Ship.clean(value)
        results = []

        if len(clean) < self.MIN_AC_LENGTH:
            return results

        for ship in ships.values():
            tl = ship.tl(interaction)
            if clean in tl["clean_short"] or clean in tl["clean_full"]:
                results.append(app_commands.Choice(name=tl["full"], value=ship.index))

                if len(results) == self.MAX_AC_RESULTS:
                    break

        return results

    async def transform(self, interaction: discord.Interaction, value: str) -> Ship:
        if ship := ships.get(value.upper(), None):
            return ship

        clean = Ship.clean(value)
        results = []

        for ship in ships.values():
            tl = ship.tl(interaction)

            if clean == tl["clean_short"] or clean == tl["clean_full"]:
                return ship

            if clean in tl["clean_short"] or clean in tl["clean_full"]:
                if len(results) == self.CUTOFF:
                    raise errors.CustomError(
                        f">5 ships returned by query `{value}`. Please refine your search."
                    )

                results.append(ship)

        if not results:
            raise errors.CustomError(f"No ships returned by query `{value}`.")
        elif len(results) > 1:
            raise errors.CustomError(
                f"Multiple ships returned by query `{value}`. "
                "Please refine your search.\n"
                + "\n".join(f"- {ship.tl(interaction)['full']}" for ship in results)
            )
        else:
            return results.pop()
