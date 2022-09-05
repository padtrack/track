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
    generated_indexes = set(ship["index"] for ship in generated)
    existing_indexes = set(ship["index"] for ship in existing)
    print(
        "\n".join(
            next(
                f'{index} {ship["translations"]["en"]["full"]}'
                for ship in generated
                if ship["index"] == index
            )
            for index in generated_indexes - existing_indexes
        )
    )
