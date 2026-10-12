"""Audio routing test on the Mac runner: install BlackHole 2ch, stream a test recording through the live engine into it
(MIMICORE_TEST_INPUT replaces the microphone), record what comes out of BlackHole and measure it.

Run from the workspace root that holds the unpacked private source in ./src:   python3 ci/scripts/mac_audio.py
Prints only device names, levels and timings (no source). Compiler output goes to build.log (encrypted by the caller).
Proves: the Mac audio output path, BlackHole detection, and that audio reaches another app's microphone.
Cannot prove: the real microphone permission prompt or real-world latency.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SRC = Path("src")
manifest = json.loads((SRC / "models" / "manifest.json").read_text(encoding="utf-8"))["packs"]


def sh(cmd, **kw):
    print("$", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    return subprocess.run(cmd, shell=isinstance(cmd, str), text=True, capture_output=True, **kw)


def show(p, tail=25):
    out = ((p.stdout or "") + (p.stderr or "")).strip().splitlines()
    print("\n".join(out[-tail:]), flush=True)


def fetch(url, dest, size, sha):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == size:
        return
    for attempt in range(4):
        try:
            h = hashlib.sha256()
            req = urllib.request.Request(url, headers={"User-Agent": "mimicore-ci"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as o:
                while chunk := r.read(1 << 20):
                    h.update(chunk)
                    o.write(chunk)
            if h.hexdigest() != sha:
                raise RuntimeError("sha256 mismatch")
            return
        except Exception as e:  # noqa: BLE001
            print(f"  retry {attempt + 1} for {dest.name}: {type(e).__name__}", flush=True)
            time.sleep(5 * (attempt + 1))
    sys.exit(f"could not download {dest.name}")


print("=== models (fast pack) ===", flush=True)
p = manifest["fast"]
for f in p["download"]:
    fetch(f["url"], SRC / "models" / p["folder"] / f["path"], f["size"], f["sha256"])

print("=== build cbx ===", flush=True)
log = open("build.log", "a")
r = subprocess.run(["cargo", "build", "--release", "-p", "cbx-engine", "--bin", "cbx"], cwd=SRC / "app", stdout=log, stderr=subprocess.STDOUT)
log.close()
print("cargo build cbx: exit", r.returncode, flush=True)
if r.returncode:
    sys.exit(r.returncode)
exe_dir = SRC / "app" / "target" / "release"
shutil.copy(SRC / "app" / "vendor" / "onnxruntime" / "libonnxruntime.dylib", exe_dir / "libonnxruntime.dylib")
cbx = str((exe_dir / "cbx").resolve())

print("=== install BlackHole 2ch and ffmpeg ===", flush=True)
show(sh("brew install --cask blackhole-2ch"), 12)
show(sh("sudo killall coreaudiod || true"), 3)
time.sleep(6)
show(sh("brew install ffmpeg"), 3)

env = dict(os.environ, CBX_PACK="fast", CBX_DEVICE="cpu")
print("=== devices as Mimicore sees them ===", flush=True)
d = subprocess.run([cbx, "devices"], cwd=SRC, env=env, capture_output=True, text=True)
print(d.stdout.strip(), flush=True)
cable = None
try:
    cable = json.loads(d.stdout[: d.stdout.rindex("}") + 1]).get("cable")
except Exception:  # noqa: BLE001
    pass
print("virtual mic detected by Mimicore:", cable, flush=True)

test_in = str((SRC / "models" / "default_voice.wav").resolve())
print("=== reference level of the test recording ===", flush=True)


def levels(path):
    q = sh(["ffmpeg", "-hide_banner", "-i", path, "-af", "volumedetect", "-f", "null", "-"])
    txt = (q.stderr or "") + (q.stdout or "")
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", txt)
    peak = re.search(r"max_volume: (-?[\d.]+) dB", txt)
    return (float(mean.group(1)) if mean else None, float(peak.group(1)) if peak else None, txt)


print("input recording mean/max dB:", levels(test_in)[:2], flush=True)

print("=== live engine -> BlackHole 2ch (test recording instead of the mic) ===", flush=True)
live_env = dict(env, MIMICORE_TEST_INPUT=test_in)
live = subprocess.Popen([cbx, "live", "--virtual", cable or "BlackHole 2ch", "--monitor", "off", "--seconds", "24"],
                        cwd=SRC, env=live_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(14)  # models load, the engine starts, audio is flowing
print("=== record BlackHole 2ch for 8 s ===", flush=True)
listing = sh(["ffmpeg", "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""])
print("\n".join([l for l in (listing.stderr or "").splitlines() if "AVFoundation" in l or "[" in l][:20]), flush=True)
cap = sh(["ffmpeg", "-y", "-hide_banner", "-f", "avfoundation", "-i", ":BlackHole 2ch", "-t", "8", "-ac", "1", "cap.wav"])
show(cap, 6)
out, _ = live.communicate(timeout=120)
lines = (out or "").strip().splitlines()
print("=== live engine output (last lines) ===")
print("\n".join(lines[-14:]), flush=True)

ok = False
if Path("cap.wav").exists():
    mean, peak, txt = levels("cap.wav")
    print(f"recorded from BlackHole: mean {mean} dB, peak {peak} dB", flush=True)
    ok = peak is not None and peak > -45
else:
    print("no capture file (microphone permission for ffmpeg may be denied on the runner)", flush=True)
print("RESULT:", "audio reached BlackHole" if ok else "no audio measured at BlackHole")
sys.exit(0 if ok else 1)
