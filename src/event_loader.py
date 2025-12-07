import json
from pathlib import Path


def load_event_json(path: Path):
    with open(path, "r") as f:
        data = json.load(f)
    return data
