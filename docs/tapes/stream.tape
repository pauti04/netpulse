# NetPulse 'stream' subcommand recording.
#
# Re-render with:  vhs docs/tapes/stream.tape
# Output:          docs/img/stream.gif
#
# The 'netpulse stream' command connects to the RIPE RIS Live WebSocket
# and runs detectors over a rolling window. Recording shows real BGP
# updates flowing in and the MOAS detector firing on real anycast /
# multi-homed prefixes (Google AS15169/19527, Cloudflare, etc.).

Output docs/img/stream.gif

Set Theme "Dracula"
Set FontSize 12
Set Width 1200
Set Height 720
Set TypingSpeed 35ms
Set Padding 12

Type "# Live BGP detection against the RIPE RIS Live WebSocket."
Sleep 600ms
Enter
Type "# Press Ctrl+C to stop."
Sleep 400ms
Enter
Sleep 300ms

Type "uv run netpulse stream --window 30s --interval 5s"
Sleep 200ms
Enter

# Let the connection establish and the first eval happen
Sleep 14s

# Gracefully stop
Ctrl+c
Sleep 800ms
