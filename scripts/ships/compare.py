import json
import os


GENERATED_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../generated/ships.json"
)
EXISTING_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../../bot/assets/public/ships.json"
)

with (open(GENERATED_PATH) as fp1, open(EXISTING_PATH) as fp2):
    generated, existing = json.load(fp1), json.load(fp2)
    new, changed = [], []

    for data in generated:
        key = data["index"]

        try:
            ship = next(ship for ship in existing if ship["index"] == key)

            if data["group"] != ship["group"]:
                changed.append(data)
        except StopIteration:
            new.append(data)

    for data in new:
        print(f"New Ship: {data['index']} {data['translations']['en']['full']}")

    for data in changed:
        ship = next(ship for ship in existing if ship["index"] == data["index"])

        print(
            f"Changed Group: {data['index']} {data['translations']['en']['full']: <20} "
            f"{ship['group']: <16} -> {data['group']: <16}"
        )
