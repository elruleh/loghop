# loghop demo - MP4 with synchronized captions
# Output: loghop-quickstart.mp4 (~25-30s target)

Output loghop-quickstart.mp4

Set Shell bash
Set FontSize 18
Set Width 1280
Set Height 720
Set Padding 25
Set Theme "Dracula"
Set TypingSpeed 15ms
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

# === SCENE 1: Title (0-3s) ===
Type "echo '  loghop — switch AI coding assistants without losing context  '"
Enter
Sleep 2s
Type "clear"
Enter
Sleep 200ms

# === SCENE 2: Set the goal (3-7s) ===
Type "echo '▸ 1. Set the project goal once'; loghop goal"
Enter
Sleep 3s

# === SCENE 3: Status (7-11s) ===
Type "echo '▸ 2. loghop tracks your project timeline'; loghop status"
Enter
Sleep 3s

# === SCENE 4: Sessions (11-16s) ===
Type "echo '▸ 3. Every session is captured, across providers'; loghop sessions list"
Enter
Sleep 4s

# === SCENE 5: Handoffs (16-21s) ===
Type "echo '▸ 4. Handoffs carry context to the next run'; loghop handoff list"
Enter
Sleep 4s

# === SCENE 6: Outro (21-25s) ===
Type "clear"
Enter
Sleep 200ms
Type "echo 'pipx install loghop  →  github.com/elruleh/loghop'"
Enter
Sleep 3s
