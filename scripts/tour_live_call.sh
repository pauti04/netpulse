#!/usr/bin/env bash
# Helper used by docs/tapes/tour.tape: a one-line curl to the live
# /detect/bgp endpoint. Kept in a script so the tape doesn't need
# escaped quotes inside Type "...".
set -euo pipefail
curl -s -X POST https://netpulse-pauti.fly.dev/detect/bgp \
    -H 'Content-Type: application/json' \
    -d '{"start_iso":"2008-02-24T18:45:00Z","duration_s":300}' \
    | jq '{alert_count: (.alerts | length), first_alert: .alerts[0]}'
