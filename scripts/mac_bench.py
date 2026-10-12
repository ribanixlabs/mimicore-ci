"""Benchmark the instant-voice engine on the Mac runner (CPU only), using the app's own auto-benchmark.

Run from the workspace root that holds the unpacked private source in ./src:
    python3 ci/scripts/mac_bench.py balanced fast

Prints only benchmark numbers (no source). Compiler output goes to an encrypted log like the app build.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SRC = Path("src")
packs = sys.argv[1:] or ["balanced"]
manifest = json.loads((SRC / "models" / "manifest.json").read_text(encoding="utf-8"))["packs"]


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


t0 = time.time()
for pid in packs:
    p = manifest[pid]
    total = sum(f["size"] for f in p["download"])
    print(f"model pack {pid}: {len(p['download'])} files, {total / 1e9:.2f} GB", flush=True)
    for f in p["download"]:
        fetch(f["url"], SRC / "models" / p["folder"] / f["path"], f["size"], f["sha256"])
print(f"models ready in {time.time() - t0:.0f}s", flush=True)

# build the CLI (output encrypted by the caller's logging: here it simply goes to the log file)
log = open("build.log", "a")
r = subprocess.run(["cargo", "build", "--release", "-p", "cbx-engine", "--bin", "cbx"], cwd=SRC / "app", stdout=log, stderr=subprocess.STDOUT)
log.close()
print("cargo build cbx: exit", r.returncode, flush=True)
if r.returncode:
    sys.exit(r.returncode)

exe_dir = SRC / "app" / "target" / "release"
shutil.copy(SRC / "app" / "vendor" / "onnxruntime" / "libonnxruntime.dylib", exe_dir / "libonnxruntime.dylib")
cbx = str((exe_dir / "cbx").resolve())
voices = str(Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve() / "voices")
shutil.rmtree(voices, ignore_errors=True)


def cbx_run(pack, *args, coreml=None):
    env = dict(os.environ, CBX_PACK=pack, CBX_DEVICE="cpu")
    if coreml:  # experimental CoreML (GPU / Neural Engine) instead of the CPU
        env.pop("CBX_DEVICE")
        env["MIMICORE_COREML"] = "1"
        env["MIMICORE_COREML_UNITS"] = coreml
    t = time.time()
    try:
        p = subprocess.run([cbx, *args], cwd=SRC, env=env, capture_output=True, text=True, timeout=1500)
    except subprocess.TimeoutExpired as e:
        print(f"--- [{pack}] cbx {' '.join(args)}  TIMED OUT after 1500 s", flush=True)
        print((e.stderr or b"").decode(errors="replace")[-600:] if isinstance(e.stderr, bytes) else (e.stderr or "")[-600:], flush=True)
        return 1
    print(f"--- [{pack}] cbx {' '.join(args)}  (exit {p.returncode}, {time.time() - t:.0f}s)")
    print(p.stdout.strip())
    # stderr carries progress lines; keep the tail
    err = p.stderr.strip().splitlines()
    print("\n".join(err[-12:]), flush=True)
    return p.returncode


# enrolment needs at least 10 s of speech: the built-in 7.4 s sample played twice
import struct
raw = (SRC / "models" / "default_voice.wav").read_bytes()
pos, out = 12, None
while pos + 8 <= len(raw):
    cid, size = raw[pos:pos + 4], struct.unpack("<I", raw[pos + 4:pos + 8])[0]
    if cid == b"data":
        data = raw[pos + 8:pos + 8 + size]
        head = raw[12:pos]                      # fmt (and any other chunks before data)
        body = head + b"data" + struct.pack("<I", size * 2) + data + data
        out = b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body
        break
    pos += 8 + size + (size & 1)
assert out, "no data chunk"
(SRC / "models" / "ci_voice.wav").write_bytes(out)

print("=== machine ===", flush=True)
subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string", "hw.ncpu", "hw.memsize"])
rc = 0
for pid in packs:
    rc |= cbx_run(pid, "devices")
    rc |= cbx_run(pid, "enroll", "--audio", "models/ci_voice.wav", "--name", "ci", "--voices", voices)
    rc |= cbx_run(pid, "bench", "--auto", "--full", "--voice", "ci", "--voices", voices)

if os.environ.get("COREML", "yes") == "yes":
    for units in ("all", "gpu"):
        print(f"=== CoreML experiment, compute units: {units} ===", flush=True)
        cbx_run("balanced", "devices", coreml=units)
        cbx_run("balanced", "bench", "--auto", "--voice", "ci", "--voices", voices, coreml=units)
sys.exit(rc)
