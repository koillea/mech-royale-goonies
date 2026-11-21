"""Entrypoint: python3 -u bot/main.py (the Dockerfile runs this). M1: minimal cube-first bot."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mechfight as mf  # noqa: E402
from m1 import M1Bot  # noqa: E402

mf.run(M1Bot)
