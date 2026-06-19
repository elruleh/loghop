# loghop dashboard demo - terminal dashboard view
# Output: loghop-dashboard-demo.mp4
# Strategy: the Textual TUI uses the alt-screen which `vhs` cannot
# capture reliably into a single PNG/MP4 frame stream. Instead we
# showcase the textual `loghop` dashboard (the same data, rendered in
# the same dark editorial palette, formatted by Rich). The TUI proper
# is demonstrated in the README link to `docs/tui.html`.

Output loghop-dashboard-demo.mp4

Set Shell bash
Set FontSize 18
Set Width 1280
Set Height 720
Set Padding 25
Set Theme "Dracula"
Set TypingSpeed 10ms
Set Framerate 30
Set WindowBar "Rings"
Set WindowBarSize 36

# Setup env (hidden, fast)
Hide
Type "export PATH=$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp/loghop-demo-recording"
Enter
Type "clear"
Enter
Show
Sleep 400ms

# Compact dashboard — the default first impression
Type "loghop"
Enter
Sleep 2.6s
Type "clear"
Enter
Sleep 200ms

# Re-run with --plain for a no-color capture-stable view
Type "loghop --plain"
Enter
Sleep 2.6s
