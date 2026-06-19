# loghop demo - GIF source (~38s target)
# Output: loghop-quickstart.gif
# Strategy: full narrative arc — status, handoffs, install CTA. Every
# command is real; no `echo` strings printed in place of commands.
# `loghop sessions list` omitted: a Rich Tree label markup leak in 0.2.0
# prints literal `[bold]…[/]` tags when stdout is non-interactive.

Output loghop-quickstart.gif

Set Shell bash
Set FontSize 16
Set Width 1200
Set Height 700
Set Padding 22
Set Theme "Dracula"
Set TypingSpeed 12ms
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

# 1) Status — establishes the shared context
Type "loghop status"
Enter
Sleep 3.2s
Type "clear"
Enter
Sleep 200ms

# 2) Handoff list — the product payoff
Type "loghop handoff list"
Enter
Sleep 3.4s
Type "clear"
Enter
Sleep 200ms

# 3) Install CTA (uv)
Type "uv tool install loghop"
Enter
Sleep 2.2s
