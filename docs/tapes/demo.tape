# NetPulse demo recording.
#
# Re-render with:  vhs docs/tapes/demo.tape
# Output:          docs/img/demo.gif
#
# The 'netpulse demo' command runs the YouTube/Pakistan 2008 hijack
# benchmark against the bundled real-data fixture in under a second.

Output docs/img/demo.gif

Set Theme "Dracula"
Set FontSize 13
Set Width 1180
Set Height 720
Set TypingSpeed 35ms
Set Padding 16

Type "# Catch the canonical 2008 BGP hijack against real RRC00 archive data."
Sleep 800ms
Enter
Type "# No setup, no native libs, ~1 second."
Sleep 600ms
Enter
Sleep 400ms

Type "uv run netpulse demo"
Sleep 300ms
Enter
Sleep 4s
