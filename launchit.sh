#!/usr/bin/env bash
# Read build log on stdin (e.g. python3 build.py ... 2>&1 | ./launchit.sh),
# echo it live to stdout, and on "Finished building:" lines run submit.py.
#
# Uses a FIFO + wait instead of tee >(...) so submit.py finishes (and its stdout
# is flushed) before the script exits; otherwise the shell prompt can appear first.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
FIFO="$WORKDIR/fifo"
mkfifo -m 600 "$FIFO"

# Reader must open the FIFO before tee can proceed; runs submit before we exit.
(
  sed -n '/Finished building:/s/^Finished building:[[:space:]]*//p' < "$FIFO" | while IFS= read -r exe; do
    [[ -z "$exe" ]] && continue
    PYTHONUNBUFFERED=1 python3 -u submit.py "bin/${exe}" mini 0 </dev/null
  done
) &
reader_pid=$!

tee "$FIFO"
wait "$reader_pid"

# Build tools often end with \r-only progress lines or no trailing \n.
printf '\n'
