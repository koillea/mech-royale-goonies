"""Entrypoint: python3 -u bot/main.py (the Dockerfile runs this)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mechfight as mf  # noqa: E402
from mechbot import MechBot  # noqa: E402

mf.run(MechBot)
