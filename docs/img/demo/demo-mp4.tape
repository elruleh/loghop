# loghop quickstart demo - short MP4 hero (~16s target)
# Output: loghop-quickstart.mp4
# Strategy: real loghop commands against a seeded multi-project workspace.
# Each command produces visible Rich output (status, sessions, handoffs)
# with enough dwell time so the rendered output is legible in the video.

Output loghop-quickstart.mp4

Set Shell bash
Set FontSize 17
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 11ms
Set Framerate 30
Set WindowBar "Rings"
Set WindowBarSize 36

# Setup env (hidden, fast): put the editable loghop on PATH and jump
# into the seeded audit project so every command has real data.
Hide
Type "export PATH=/home/user/projects/loghop/.venv/bin:$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp/loghop-demo-projects/audit"
Enter
Type "clear"
Enter
Show
Sleep 300ms

# 1) Global dashboard — six real projects with sessions and handoffs
Type "loghop projects"
Enter
Sleep 3.4s
Type "clear"
Enter
Sleep 250ms

# 2) Project status — goal, providers, memory, handoff pointer
Type "loghop status"
Enter
Sleep 3.2s
Type "clear"
Enter
Sleep 250ms

# 3) Sessions timeline — the product payoff: history travels between runs
Type "loghop sessions list"
Enter
Sleep 3.8s
Type "clear"
Enter
Sleep 250ms

# 4) Handoff list — built handoffs ready to resume on another provider
Type "loghop handoff list"
Enter
Sleep 3.2s
