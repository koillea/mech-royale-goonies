"""Repository quality gate: run before every submission (Mech Royale allows 4 an hour, spend them well).

    python3 tools/quality_gate.py            # tests + static checks + conformance check
    python3 tools/quality_gate.py --docker   # also build the image and check it in the match sandbox

1. pytest (offline, deterministic, uses the kit's recorded match);
2. static checks: standard library only, nothing printed to stdout from bot code (stdout is the protocol),
   Dockerfile at the top level, repository under the 20 MB submission cap;
3. kit/check/check.py against the bot run locally;
4. with --docker: docker build, then check.py against the image with the exact sandbox flags the scorer uses.
Exit status is non-zero if anything fails.
"""
from __future__ import annotations

import argparse
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STDLIB = set(sys.stdlib_module_names) | {"mechfight", "mechbot"}
SANDBOX = ["docker", "run", "--rm", "-i", "--network", "none", "--cpus", "1", "--memory", "512m", "--read-only",
           "--tmpfs", "/tmp:rw,size=64m", "--user", "65534:65534", "-v", f"{ROOT / 'arena'}:/arena:ro", "goonies-bot"]


def run(cmd, timeout=600):
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def static_checks() -> list:
    problems = []
    for py in (ROOT / "bot").rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for n in names:
                    if node.__class__ is ast.ImportFrom and node.level:
                        continue
                    if n.split(".")[0] not in STDLIB:
                        problems.append(f"{py.relative_to(ROOT)}: non-stdlib import {n}")
            if py.name != "mechfight.py" and isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print":
                if not any(k.arg == "file" for k in node.keywords):
                    problems.append(f"{py.relative_to(ROOT)}:{node.lineno}: print() to stdout breaks the protocol")
    if not (ROOT / "Dockerfile").exists():
        problems.append("Dockerfile missing at the top level")
    size = sum(f.stat().st_size for f in ROOT.rglob("*") if f.is_file() and ".git" not in f.parts)
    if size > 20 * 1024 * 1024:
        problems.append(f"repository is {size / 1e6:.1f} MB, over the 20 MB cap")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docker", action="store_true", help="also build and check the image in the match sandbox")
    args = ap.parse_args()
    fails = []

    print("== pytest")
    code, out = run([sys.executable, "-m", "pytest"])
    print("  ", out.strip().splitlines()[-1] if out.strip() else "(no output)")
    if code:
        fails.append("pytest")
        print(out[-3000:])

    print("== static checks")
    probs = static_checks()
    for p in probs:
        print("  ", p)
    print("   ok" if not probs else "", end="\n" if not probs else "")
    if probs:
        fails.append("static checks")

    print("== conformance (local)")
    code, out = run([sys.executable, "kit/check/check.py", "--", sys.executable, "-u", "bot/main.py"])
    for line in out.splitlines():
        if line.startswith(("observations", "answer time", "PASS", "FAIL")):
            print("  ", line)
    if code:
        fails.append("check.py local")
        print(out[-2000:])

    if args.docker:
        print("== docker build")
        code, out = run(["docker", "build", "-q", "-t", "goonies-bot", "."])
        print("   ok" if code == 0 else out[-2000:])
        if code:
            fails.append("docker build")
        else:
            print("== conformance (match sandbox)")
            code, out = run([sys.executable, "kit/check/check.py", "--map-dir", "/arena", "--", *SANDBOX])
            for line in out.splitlines():
                if line.startswith(("observations", "answer time", "PASS", "FAIL")):
                    print("  ", line)
            if code:
                fails.append("check.py docker")
                print(out[-2000:])

    print("== result")
    if fails:
        print("   FAIL:", ", ".join(fails))
        return 1
    print("   all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
