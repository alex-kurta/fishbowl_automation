#!/usr/bin/env bash
# Resurrects the poller if it is gone. Run from cron every minute.
#
# Deliberately never kills anything: data/auto_order_entry.lock would refuse a second
# instance anyway, and killing mid-import is worse than a delayed restart. If the lock
# is stale from a hard kill, the poller's own stale check clears it on the next attempt.

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
mkdir -p "$APP_DIR/data/logs"

# The [a] trick stops pgrep from matching this script's own command line.
if pgrep -f "[a]uto_order_entry.py --interval" > /dev/null 2>&1; then
    exit 0
fi

echo "$(date -Is) poller not running, restarting"
nohup "$APP_DIR/scripts/run_order_entry.sh" \
    >> "$APP_DIR/data/logs/supervisor.log" 2>&1 &
