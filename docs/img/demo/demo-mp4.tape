# loghop demo - short MP4 hero (~18s target)
# Output: loghop-quickstart.mp4
# Strategy: run real loghop commands in a pre-populated demo project,
# so the screen shows real output, not echoed strings. `loghop sessions
# list` is omitted because of a Rich markup leak in 0.2.0 (tracked).

Output loghop-quickstart.mp4

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
Sleep 300ms

# Show the shared project context
Type "loghop status"
Enter
Sleep 2.6s
Type "clear"
Enter
Sleep 200ms

# Show the handoff list — the core idea: history travels between runs
Type "loghop handoff list"
Enter
Sleep 2.8s
Type "clear"
Enter
Sleep 200ms

# Closing CTA: real install command (uv is available in our recording env)
Type "uv tool install loghop"
Enter
Sleep 2.6s
