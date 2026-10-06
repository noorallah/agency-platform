#!/usr/bin/env bash
# Run one click flow in the real desktop app against a running backend.
#
#   integration_test/run.sh sign_in_flow_test.dart [http://127.0.0.1:8000]
#
# Run from desktop/ (Git Bash). It gives the app a scratch settings folder and
# a file-backed sign-in, so a person's own preferences and saved sign-in are
# never read or replaced, and every run starts signed out. The app does not
# always close itself when a flow ends, so the run is cut off after LIMIT
# seconds and the copy it started is stopped. Sign in as another user with
# IT_EMAIL and IT_PASSWORD in the environment.
set -u
FLOW="${1:?name a flow file under integration_test/}"
API="${2:-http://127.0.0.1:8000}"
LIMIT="${LIMIT:-480}"
SCRATCH="${TEMP:-/tmp}/agency-it-appdata"
LOG="${TEMP:-/tmp}/agency-it-${FLOW%.dart}.log"

rm -rf "$SCRATCH" && mkdir -p "$SCRATCH"
APPDATA="$(cygpath -w "$SCRATCH")" timeout "$LIMIT" flutter test \
  "integration_test/$FLOW" -d windows --reporter expanded \
  --dart-define=API_BASE_URL="$API" --dart-define=SESSION_STORE=file \
  ${IT_EMAIL:+--dart-define=IT_EMAIL="$IT_EMAIL"} \
  ${IT_PASSWORD:+--dart-define=IT_PASSWORD="$IT_PASSWORD"} \
  >"$LOG" 2>&1
STATUS=$?

# Only the copy built from this checkout, never one a person has open.
HERE="$(cygpath -w "$PWD")"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='agency_desktop.exe'\" | Where-Object { \$_.ExecutablePath -like '$HERE*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1

grep -E "^[0-9]+:[0-9]+ \+|Timed out|On screen:|SIGNED IN|FLOW:|Some tests failed|All tests passed" "$LOG" | cut -c1-2000 | tail -120
echo "exit $STATUS, log $LOG"
exit "$STATUS"
