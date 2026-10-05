"""Early-build version helpers for the beta workflow (no dependencies).

    python scripts/version.py next  <src-dir>        -> prints "<current> <next early-build version>"
    python scripts/version.py apply <src-dir> <new>  -> writes <new> into the 3 version files of the checkout

Rules: 2.6.0 -> 2.6.1-beta.1, then 2.6.1-beta.2 ... (the version files on `develop` carry the last early build).
"""
import json
import re
import sys
from pathlib import Path

FILES = ("app/desktop/src-tauri/tauri.conf.json", "app/desktop/package.json", "app/Cargo.toml")
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-beta\.(\d+))?$")


def current(src: Path) -> str:
    return json.loads((src / FILES[0]).read_text(encoding="utf-8"))["version"]


def next_version(cur: str) -> str:
    m = SEMVER.match(cur)
    if not m:
        raise SystemExit(f"unexpected version {cur!r}")
    a, b, c, n = int(m[1]), int(m[2]), int(m[3]), m[4]
    return f"{a}.{b}.{c}-beta.{int(n) + 1}" if n else f"{a}.{b}.{c + 1}-beta.1"


def apply(src: Path, new: str) -> None:
    if not SEMVER.match(new):
        raise SystemExit(f"refusing to write version {new!r}")
    cur = current(src)
    for rel in FILES:
        f = src / rel
        with open(f, encoding="utf-8", newline="") as h:
            s = h.read()
        s2 = s.replace(f'"version": "{cur}"', f'"version": "{new}"', 1) if rel.endswith(".json") else s.replace(f'version = "{cur}"', f'version = "{new}"', 1)
        if s2 == s:
            raise SystemExit(f"version {cur} not found in {rel}")
        with open(f, "w", encoding="utf-8", newline="") as h:
            h.write(s2)


if __name__ == "__main__":
    cmd, src = sys.argv[1], Path(sys.argv[2])
    if cmd == "next":
        cur = current(src)
        print(cur, next_version(cur))
    elif cmd == "apply":
        apply(src, sys.argv[3])
    else:
        raise SystemExit("usage: version.py next|apply ...")
