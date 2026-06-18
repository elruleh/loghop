# loghop demo
Output demo.gif

Set Shell bash
Set FontSize 14
Set Width 1200
Set Height 700
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 50ms
Set Framerate 30

# Set up env (silent)
Type "export PATH=$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp/loghop-demo-recording"
Enter
Type "clear"
Enter
Sleep 1s

# Step 1: Show goal
Type "loghop goal"
Enter
Sleep 3s

# Step 2: Status
Type "loghop status"
Enter
Sleep 4s

# Step 3: Sessions list
Type "loghop sessions list"
Enter
Sleep 5s

# Step 4: List handoffs
Type "loghop handoff list"
Enter
Sleep 5s

# Step 5: Show latest handoff
Type "loghop handoff show H-002"
Enter
Sleep 5s

# Closing
Type "echo 'pipx install loghop'"
Enter
Sleep 1s
Type "echo 'github.com/elruleh/loghop'"
Enter
Sleep 3s
