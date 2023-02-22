import functools
import json
import os
import pickle
import struct
import zlib

import polib

ENCODING = "latin1"
KEYS = (
    "id",
    "index",
    "isPaperShip",
    "group",
    "level",
    "name",
    "typeinfo.species",
    "typeinfo.nation",
)
GAMEPARAMS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../resources/GameParams.data"
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../generated/ships.json"
)
TEXTS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../resources/texts"
)

translations = {}


def rgetattr(obj, attr, *args):
    """
    https://stackoverflow.com/questions/31174295/getattr-and-setattr-on-nested-objects
    """

    def _getattr(_obj, _attr):
        return getattr(_obj, _attr, *args)

    return functools.reduce(_getattr, [obj] + attr.split("."))


def get_translations(index: str) -> dict[str, dict[str, str]]:
    return {
        locale: {
            "short": messages.get(f"IDS_{index}", None),
            "full": messages.get(f"IDS_{index}_FULL", None),
        }
        for locale, messages in translations.items()
    }


def main():
    print("Loading translations...")
    for locale in sorted(os.listdir(TEXTS_PATH)):
        mo_file = polib.mofile(f"{TEXTS_PATH}/{locale}/LC_MESSAGES/global.mo")
        translations[locale] = {entry.msgid: entry.msgstr for entry in mo_file}

    print("Loading GameParams...")
    with open(GAMEPARAMS_PATH, "rb") as fp:
        gp_data: bytes = fp.read()

    gp_data: bytes = struct.pack("B" * len(gp_data), *gp_data[::-1])
    gp_data: bytes = zlib.decompress(gp_data)
    gp_data: dict = pickle.loads(gp_data, encoding=ENCODING)[0]

    ships = []
    for index, entity in gp_data.items():
        if entity.typeinfo.type == "Ship":
            data = {key[key.rfind(".") + 1 :]: rgetattr(entity, key) for key in KEYS}
            data["translations"] = get_translations(entity.index)
            ships.append(data)

    with open(OUTPUT_PATH, "w") as fp:
        json.dump(ships, fp, indent=4)

    print("Done!")


if __name__ == "__main__":
    main()
