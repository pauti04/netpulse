# NetPulse end-to-end tour recording.
#
# Re-render with:  vhs docs/tapes/tour.tape
# Output:          docs/img/tour.gif
#
# Walks a first-time visitor through:
#   1. The 5-incident demo list (--list).
#   2. The YouTube 2008 hijack demo (story + path + verdict).
#   3. The 2018 MainOne leak demo (LEAK DETECTED verdict).
#   4. The 5-incident corpus benchmark (5/5 TP).
#   5. The per-record streaming-mode latency benchmark.
#   6. The live HTTP /detect/bgp endpoint.

Output docs/img/tour.gif

Set Theme "Dracula"
Set FontSize 12
Set Width 1320
Set Height 920
Set TypingSpeed 28ms
Set Padding 14

Type "# 1. Five labeled incidents the demo can replay against real archive data."
Sleep 700ms
Enter
Type "uv run netpulse demo --list"
Sleep 250ms
Enter
Sleep 4s

Type "clear"
Sleep 150ms
Enter

Type "# 2. Default demo: 2008 YouTube hijack -- HIJACK DETECTED panel."
Sleep 700ms
Enter
Type "uv run netpulse demo"
Sleep 250ms
Enter
Sleep 6s

Type "clear"
Sleep 150ms
Enter

Type "# 3. 2018 MainOne leak: LEAK DETECTED via valley-free + customer-cone."
Sleep 700ms
Enter
Type "uv run netpulse demo --incident mainone_google_leak_2018"
Sleep 250ms
Enter
Sleep 7s

Type "clear"
Sleep 150ms
Enter

Type "# 4. Corpus benchmark: 5 labeled incidents, 5/5 TP / 0 FN / 0 GAP."
Sleep 700ms
Enter
Type "uv run python scripts/run_corpus_benchmark.py | tail -25"
Sleep 250ms
Enter
Sleep 8s

Type "clear"
Sleep 150ms
Enter

Type "# 5. Streaming-mode latency benchmark: 0us from documented onset."
Sleep 700ms
Enter
Type "uv run netpulse benchmark stream-latency --incidents data/incidents --baseline data/baselines/yt_rib_filtered.duckdb"
Sleep 250ms
Enter
Sleep 7s

Type "clear"
Sleep 150ms
Enter

Type "# 6. Live HTTP API on Fly.io: same detectors, JSON response."
Sleep 700ms
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
