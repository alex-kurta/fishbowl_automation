#!/usr/bin/env bash
# Starts the resident poller: one process, one Fishbowl login, 5s tick.
#
# cron gives a minimal environment, so set everything explicitly instead of trusting
# the caller's shell. Keep LF line endings: CRLF makes bash fail on $'\r'.
#
#   --interval 5 : re-poll every 5s in the same process (warm poll is ~73ms)
#   --quiet      : no console output, no idle "found 0" log lines. Imports, skips,
#                  failures and tracebacks still reach data/logs/auto_order_entry.log.

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$APP_DIR"

export PATH="/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1

exec "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/auto_order_entry.py" \
  --interval "${POLL_INTERVAL:-5}" --quiet
