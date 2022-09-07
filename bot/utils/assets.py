import json
import os

_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../assets/hosted/manifest.json"
)

with open(_MANIFEST_PATH) as fp:
    manifest = json.load(fp)


def get(asset: str) -> str:
    return manifest.get(asset)
