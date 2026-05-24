# NetPulse demo recording.
#
# Re-render with:  vhs docs/tapes/demo.tape
# Output:          docs/img/demo.gif
#
# The `netpulse demo` command replays the YouTube/Pakistan 2008 hijack
# against the bundled real-data fixture and shows a Rich-rendered
# story panel + alert table + summary in ~1 second.

Output docs/img/demo.gif

Set Theme "Dracula"
Set FontSize 13
Set Width 1280
Set Height 920
Set TypingSpeed 32ms
Set Padding 16

Type "# Catch the canonical 2008 BGP hijack against real RRC00 archive data."
Sleep 700ms
Enter
Type "# No setup, no native libs, under one second wall."
Sleep 600ms
Enter
Sleep 300ms

Type "uv run netpulse demo"
Sleep 250ms
Enter
Sleep 5s

Type "# Replay any of the 5 labeled-incident corpus entries with --incident."
Sleep 700ms
Enter
Type "uv run netpulse demo --incident indosat_2014"
Sleep 250ms
Enter
Sleep 5s
