#!/bin/bash
# Start the built Mac app on the runner, give it time to come up, take a screenshot and show its own log.
# usage: mac_smoke.sh <dir with the .dmg>
set -u
dmg=$(ls "$1"/*.dmg | head -1)
echo "dmg: $(basename "$dmg")"
mnt="$RUNNER_TEMP/mnt"; mkdir -p "$mnt"
hdiutil attach "$dmg" -mountpoint "$mnt" -nobrowse -quiet
app="$RUNNER_TEMP/Mimicore.app"
cp -R "$mnt/Mimicore.app" "$app"
hdiutil detach "$mnt" -quiet || true
xattr -cr "$app" || true
echo "--- codesign:"; codesign -dv "$app" 2>&1 | head -5
echo "--- bundle:"; ls "$app/Contents/Resources" | head -20
echo "--- architecture:"; file "$app/Contents/MacOS/Mimicore"
export MIMICORE_HOME="$RUNNER_TEMP/mmhome"
rm -rf "$MIMICORE_HOME"; mkdir -p "$MIMICORE_HOME"
"$app/Contents/MacOS/Mimicore" > "$RUNNER_TEMP/app.out" 2>&1 &
pid=$!
sleep 40
if kill -0 "$pid" 2>/dev/null; then echo "app is running after 40 s (pid $pid)"; else echo "APP EXITED EARLY"; wait "$pid"; echo "exit code $?"; fi
mkdir -p shots
screencapture -x shots/window.png 2>&1 || echo "screencapture failed"
echo "--- app stdout/stderr (first 40 lines):"; head -40 "$RUNNER_TEMP/app.out"
echo "--- app log files:"
find "$MIMICORE_HOME" -name '*.log' | while read -r f; do echo "== $f"; head -60 "$f"; done
kill "$pid" 2>/dev/null || true
exit 0
