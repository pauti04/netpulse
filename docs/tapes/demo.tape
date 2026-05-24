# NetPulse demo recording.
#
# Re-render with:  vhs docs/tapes/demo.tape
# Output:          docs/img/demo.gif
#
# Shows three flows back-to-back:
#   1. --list enumerates the 5 curated incidents.
#   2. Default (YouTube 2008) -- story + hijacker path with friendly AS
#      names + HIJACK DETECTED verdict + 0us stream latency.
#   3. --incident all -- play all 5 with a final summary table.

Output docs/img/demo.gif

Set Theme "Dracula"
Set FontSize 12
Set Width 1340
Set Height 980
Set TypingSpeed 28ms
Set Padding 14

Type "# 5 curated BGP incidents, all replayed against real RRC00 data."
Sleep 600ms
Enter
Type "uv run netpulse demo --list"
Sleep 250ms
Enter
Sleep 4s

Type "clear"
Sleep 150ms
Enter

Type "# Default: 2008 YouTube hijack. Story -> hijacker path -> 0us detection."
Sleep 600ms
Enter
Type "uv run netpulse demo"
Sleep 250ms
Enter
Sleep 6s

Type "clear"
Sleep 150ms
Enter

Type "# Roll up all 5 incidents back-to-back."
Sleep 600ms
Enter
Type "uv run netpulse demo --incident all"
Sleep 250ms
Enter
Sleep 14s
