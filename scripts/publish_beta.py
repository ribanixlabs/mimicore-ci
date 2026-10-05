"""Publish a signed early build on the pinned prerelease `beta` of the public repo and tell the bug queue.

    python scripts/publish_beta.py --version 2.6.1-beta.1 --before 2026-10-05T10:00:00Z --dir signed [--dry]

Needs GH_TOKEN (a token that may write releases of ribanixlabs/mimicore-app) and OPS_TOKEN. `signed/` holds
Mimicore_<version>_x64-setup.exe and its .sig. The release is a prerelease and never "latest": the stable update feed and the website
download are untouched; only people who press "Check for early release" (or follow the e-mail link) get it.
"""
import argparse
import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

PUBLIC = "ribanixlabs/mimicore-app"
QUEUE = "https://evhbtofegbkvmjagsuby.supabase.co/functions/v1/bug-queue"
NOTE = "Early build {v}. Not installed automatically: Mimicore > Settings > Updates > Check for early release."


def gh(*args, check=True, dry=False):
    print(">", "gh", *args, flush=True)
    if dry:
        return subprocess.CompletedProcess(args, 0, "", "")
    return subprocess.run(["gh", *args], check=check, capture_output=False, text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--before", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--tag", default="beta", help="release tag (tests use another one)")
    ap.add_argument("--no-queue", action="store_true", help="do not tell the bug queue (tests)")
    a = ap.parse_args()
    d = Path(a.dir)
    exe = d / f"Mimicore_{a.version}_x64-setup.exe"
    sig = exe.with_name(exe.name + ".sig")
    if not exe.exists() or not sig.exists():
        sys.exit(f"missing {exe.name} or its .sig in {d}")
    signature = sig.read_text().strip()
    if not signature:
        sys.exit("empty signature")
    feed = {"version": a.version, "notes": f"Early build {a.version} with the latest fixes.",
            "pub_date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "platforms": {"windows-x86_64": {"signature": signature, "url": f"https://github.com/{PUBLIC}/releases/download/{a.tag}/{exe.name}"}}}
    latest = d / "latest.json"
    latest.write_text(json.dumps(feed, indent=2))
    alias = d / "Mimicore-beta-setup.exe"
    alias.write_bytes(exe.read_bytes())
    note = NOTE.format(v=a.version)

    have = subprocess.run(["gh", "release", "view", a.tag, "-R", PUBLIC, "--json", "assets"], capture_output=True, text=True)
    if have.returncode != 0:
        gh("release", "create", a.tag, str(exe), str(sig), str(latest), str(alias), "-R", PUBLIC, "--prerelease", "--latest=false",
           "--title", "Early builds (beta)", "--notes", note, dry=a.dry)
    else:
        old = [x["name"] for x in json.loads(have.stdout).get("assets", []) if x["name"].endswith("-setup.exe") or x["name"].endswith(".sig")]
        gh("release", "upload", a.tag, str(exe), str(sig), str(latest), str(alias), "-R", PUBLIC, "--clobber", dry=a.dry)
        for name in old:
            if name not in (exe.name, sig.name, alias.name):
                gh("release", "delete-asset", a.tag, name, "-R", PUBLIC, "--yes", check=False, dry=a.dry)
        gh("release", "edit", a.tag, "-R", PUBLIC, "--prerelease", "--latest=false", "--notes", note, dry=a.dry)
    print("published early build", a.version)
    if a.dry or a.no_queue:
        return
    import os
    req = urllib.request.Request(QUEUE, json.dumps({"action": "beta_released", "version": a.version, "before": a.before}).encode(),
                                 {"content-type": "application/json", "x-ops-token": os.environ["OPS_TOKEN"]})
    print("tickets moved to beta:", urllib.request.urlopen(req, timeout=60).read().decode())


if __name__ == "__main__":
    main()
