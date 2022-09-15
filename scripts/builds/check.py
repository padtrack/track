import os
import sys

sys.path.insert(1, os.path.join(sys.path[0], ".."))

import toml

from bot.utils import wows

BUILDS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../bot/assets/public/builds.toml"
)

with open(BUILDS_PATH) as fp:
    builds = toml.load(fp)
    mapped = set(index for value in builds.values() for index in value["ships"])


with open("acknowledged.txt") as fp:
    acknowledged = set(line[: line.index(" ")] for line in fp.readlines())

for ship in wows.ships.values():
    if ship.index not in mapped and ship.level != 1 and ship.index not in acknowledged:
        print(ship)
