"""
Quick & dirty script to check copy pasted execution log
from a Google Apps Script against builds.toml
"""

from typing import List, Tuple

import os
import toml

BUILDS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../bot/assets/public/builds.toml"
)

builds = toml.load(BUILDS_PATH)
bookmarks = set(_id for _id in builds)

with open("execution.log") as fp:
    lines: List[str] = fp.readlines()
    scraped: List[Tuple[str]] = [
        tuple(line[16:].rstrip().split(maxsplit=1)) for line in lines
    ]

    print("\n".join(f"{_id} {name}" for _id, name in scraped if _id not in bookmarks))
