"""Load any committed version of our bot (and the kit example bot) in-process, side by side.

Each version's `bot/mechbot` package is extracted from git into sim/.cache/<name>/ and imported under its own
module name, so several versions can play in one match.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tarfile
import io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "sim", ".cache")

# name -> git commit (all on koillea/mech-royale-goonies)
VERSIONS = {
    "v1": "1bc77f0",
    "v3": "5db062e",
    "v4": "9cd3063",
    "abc": "cf8d2a4",
    "v5": "a13a3b3",
    "try-b": "try-b",
    "try-c": "try-c",
    "try-d": "try-d",
}
REAL_SCORES = {"example": 1.15, "v1": 3.21, "v3": 3.52, "v4": 2.58, "abc": 2.90, "v5": 3.19}


def _extract(name: str, rev: str) -> str:
    dst = os.path.join(CACHE, name)
    if not os.path.exists(os.path.join(dst, "bot", "mechbot", "__init__.py")):
        os.makedirs(dst, exist_ok=True)
        data = subprocess.run(["git", "-C", ROOT, "archive", rev, "bot"], check=True, capture_output=True).stdout
        tarfile.open(fileobj=io.BytesIO(data)).extractall(dst)
    return dst


def load_version(name: str, rev: str = None):
    """Return the MechBot class of a committed version."""
    rev = rev or VERSIONS[name]
    modname = "mb_" + name.replace("-", "_")
    if modname in sys.modules:
        return sys.modules[modname].MechBot
    pkg = os.path.join(_extract(name, rev), "bot", "mechbot")
    spec = importlib.util.spec_from_file_location(modname, os.path.join(pkg, "__init__.py"),
                                                  submodule_search_locations=[pkg])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod.MechBot


def load_example():
    """The kit's example bot (the board's 1.15 baseline)."""
    if "kit_example" in sys.modules:
        return sys.modules["kit_example"].Bot
    kit_py = os.path.join(ROOT, "bot")
    if "mechfight" not in sys.modules:
        spec = importlib.util.spec_from_file_location("mechfight", os.path.join(kit_py, "mechfight.py"))
        mf = importlib.util.module_from_spec(spec)
        sys.modules["mechfight"] = mf
        spec.loader.exec_module(mf)
    src = open(os.path.join(ROOT, "kit", "example_bot.py")).read().replace("mf.run(Bot)", "")
    mod = type(sys)("kit_example")
    sys.modules["kit_example"] = mod
    exec(compile(src, "example_bot.py", "exec"), mod.__dict__)
    return mod.Bot


def factory(name: str):
    if name == "example":
        cls = load_example()
    else:
        cls = load_version(name)

    def make(hello):
        bot = cls(hello)
        return bot
    return make
