# `netpulse explain` — forensic propagation reconstruction.
# Re-render with:  vhs docs/tapes/explain.tape   → docs/img/explain.gif

Output docs/img/explain.gif

Set Theme "Dracula"
Set FontSize 13
Set Width 1180
Set Height 940
Set TypingSpeed 32ms
Set Padding 16

Type "# How did the 2008 YouTube hijack actually spread across the internet?"
Sleep 800ms
Enter
Type "uv run netpulse explain"
Sleep 300ms
Enter
Sleep 4s

Type "# Same machinery reconstructs a route leak (transit-AS mode):"
Sleep 800ms
Enter
Type "uv run netpulse explain --incident mainone_google_leak_2018"
Sleep 300ms
Enter
Sleep 4s
