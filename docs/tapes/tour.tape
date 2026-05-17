# NetPulse end-to-end tour recording.
#
# Re-render with:  vhs docs/tapes/tour.tape
# Output:          docs/img/tour.gif
#
# Walks a first-time visitor through:
#   1. The bundled-data demo (no native deps)
#   2. The 4-incident corpus benchmark
#   3. The per-record streaming-mode latency benchmark
#   4. The live HTTP /detect/bgp endpoint
#
# Everything runs against the bundled fixtures + the live Fly.io deployment.

Output docs/img/tour.gif

Set Theme "Dracula"
Set FontSize 12
Set Width 1280
Set Height 820
Set TypingSpeed 32ms
Set Padding 14

Type "# 1. Bundled-data demo: catches the 2008 YouTube hijack in ~1s."
Sleep 600ms
Enter
Type "uv run netpulse demo"
Sleep 250ms
Enter
Sleep 5s

Type "clear"
Sleep 150ms
Enter

Type "# 2. Corpus benchmark: 4 labeled incidents, 3 TP / 1 GAP / 0 FN."
Sleep 600ms
Enter
Type "uv run python scripts/run_corpus_benchmark.py | tail -25"
Sleep 250ms
Enter
Sleep 8s

Type "clear"
Sleep 150ms
Enter

Type "# 3. Streaming-mode latency benchmark: 0us from documented onset."
Sleep 600ms
Enter
Type "uv run netpulse benchmark stream-latency --incidents data/incidents --baseline data/baselines/yt_rib_filtered.duckdb"
Sleep 250ms
Enter
Sleep 7s

Type "clear"
Sleep 150ms
Enter

Type "# 4. Live HTTP API on Fly.io: same detectors, JSON response."
Sleep 600ms
Enter
Type "curl -s https://netpulse-pauti.fly.dev/health | jq ."
Sleep 250ms
Enter
Sleep 3s

Type "./scripts/tour_live_call.sh"
Sleep 250ms
Enter
Sleep 6s

Sleep 1s
