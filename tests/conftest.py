import gzip
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STREAM = os.path.join(ROOT, "kit", "check", "stream.jsonl.gz")


@pytest.fixture(scope="session")
def stream():
    with gzip.open(STREAM, "rt") as f:
        return [json.loads(line) for line in f]


@pytest.fixture(scope="session")
def hello(stream):
    return stream[0]


@pytest.fixture(scope="session")
def observations(stream):
    return [m for m in stream if m.get("type") == "obs"]


@pytest.fixture(scope="session")
def wm():
    from mechbot.worldmap import WorldMap
    return WorldMap(os.path.join(ROOT, "arena"))
