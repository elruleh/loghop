# loghop quickstart demo - GIF source (~34s target)
# Output: loghop-quickstart.gif
# Strategy: full narrative arc against a seeded multi-project workspace.
# Every command is real and renders visible Rich output. Ends with the
# one-line install CTA.

Output loghop-quickstart.gif

Set Shell bash
Set FontSize 15
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 12ms
Set Framerate 30
Set WindowBar "Rings"
Set WindowBarSize 34

# Setup env (hidden, fast)
Hide
Type "export PATH=/home/user/projects/loghop/.venv/bin:$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp/loghop-demo-projects/audit"
Enter
Type "clear"
Enter
Show
Sleep 400ms

# 1) Global dashboard — context: six real projects
Type "loghop projects"
Enter
Sleep 4s
Type "clear"
Enter
Sleep 250ms

# 2) Project status — goal, providers, memory, handoff pointer
Type "loghop status"
Enter
Sleep 3.6s
Type "clear"
Enter
Sleep 250ms

# 3) Sessions timeline — history travels between runs
Type "loghop sessions list"
Enter
Sleep 4.2s
Type "clear"
Enter
Sleep 250ms

# 4) Handoff list — built handoffs ready to resume
Type "loghop handoff list"
Enter
Sleep 4s
Type "clear"
Enter
Sleep 250ms

# 5) Install CTA
Type "uv tool install loghop"
Enter
Sleep 3s
