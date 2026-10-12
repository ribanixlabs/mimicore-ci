#!/bin/bash
# Build the Mac app from the unpacked private source in ./src.
#
# The source is private but this repository (and its logs) are public, and compiler messages quote source lines. So the
# full build output never reaches the public log: it is encrypted to a public key (log_pub.pem) and uploaded as an artifact
# that only the owner can decrypt. The public log only shows step names and exit codes.
set -u
here="$(cd "$(dirname "$0")/.." && pwd)"
cd src

run() { # run <label> <command...>: output goes to the encrypted log only
  local label="$1"; shift
  echo "=== $label" >> ../build.log
  "$@" >> ../build.log 2>&1
  local rc=$?
  echo "$label: exit $rc"
  return $rc
}

: > ../build.log
rc=0
run "fetch ONNX Runtime (CPU, Apple Silicon)" python3 scripts/fetch_runtime.py --mac || rc=$?
if [ $rc -eq 0 ]; then run "npm ci" bash -c 'cd app/desktop && npm ci --silent' || rc=$?; fi
if [ $rc -eq 0 ]; then run "tauri build (app + dmg)" bash -c 'cd app/desktop && npx tauri build' || rc=$?; fi
if [ $rc -eq 0 ] && [ "${RUN_TESTS:-no}" = "yes" ]; then
  run "engine tests" bash -c 'cd app && cargo test -p cbx-engine --release' || rc=$?
fi

# encrypt the log for the owner: random AES key, itself encrypted with the RSA public key
cd ..
key=$(openssl rand -hex 32)
printf '%s' "$key" > k.txt
openssl enc -aes-256-cbc -pbkdf2 -md sha256 -salt -pass file:k.txt -in build.log -out build.log.enc
openssl rsautl -encrypt -oaep -pubin -inkey "$here/log_pub.pem" -in k.txt -out k.enc
rm -f k.txt build.log
echo "build finished with exit code $rc (encrypted log: $(wc -c < build.log.enc) bytes)"
exit $rc
