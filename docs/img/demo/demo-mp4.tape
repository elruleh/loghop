# loghop demo - short MP4 hero (~18s target)
# Output: loghop-quickstart.mp4

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
Sleep 200ms

# Title
Type "echo 'loghop — keep context when switching assistants'"
Enter
Sleep 1400ms
Type "clear"
Enter
Sleep 150ms

# Goal + status
Type "echo '1) set the project goal once'; loghop goal"
Enter
Sleep 1400ms
Type "echo '2) timeline + sessions stay in sync'; loghop status"
Enter
Sleep 1400ms

# Handoff + CTA
Type "echo '3) handoff cleanly to the next run'; loghop handoff list"
Enter
Sleep 1300ms
Type "clear"
Enter
Sleep 150ms
Type "echo 'pipx install loghop  →  github.com/elruleh/loghop'"
Enter
Sleep 2200ms
