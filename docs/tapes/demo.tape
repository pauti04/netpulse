# NetPulse demo recording.
#
# Re-render with:  vhs docs/tapes/demo.tape
# Output:          docs/img/demo.gif
#
# Shows the headline-grade demo flow:
#   1. `--list` enumerates the 5 curated incidents.
#   2. Default replay (YouTube 2008) prints the story panel, the
#      actual hijacker AS path from the archive, a noise-filtered
#      alert table, and a red HIJACK DETECTED verdict.
#   3. `--incident indosat_2014` shows the 19-critical case.

Output docs/img/demo.gif

Set Theme "Dracula"
Set FontSize 13
Set Width 1280
Set Height 980
Set TypingSpeed 30ms
Set Padding 16

Type "# 5 curated BGP incidents, all replayed against real RRC00 data."
Sleep 700ms
Enter
Type "uv run netpulse demo --list"
Sleep 250ms
Enter
Sleep 4s

Type "clear"
Sleep 150ms
Enter

Type "# Default: 2008 YouTube hijack. Story -> hijacker path -> alerts -> verdict."
Sleep 700ms
Enter
Type "uv run netpulse demo"
Sleep 250ms
Enter
Sleep 6s

Type "clear"
Sleep 150ms
Enter

Type "# Indosat 2014: 19 critical alerts across both detector shapes."
Sleep 700ms
Enter
Type "uv run netpulse demo --incident indosat_2014"
Sleep 250ms
Enter
Sleep 6s
