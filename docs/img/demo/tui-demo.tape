# loghop TUI demo - sessions-focused
# Output: loghop-tui-demo.mp4

Output loghop-tui-demo.mp4

Set Shell bash
Set FontSize 16
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 14ms
Set Framerate 30
Set WindowBar "Rings"
Set WindowBarSize 36

Hide
Type "export PATH=$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp/loghop-demo-recording"
Enter
Type "clear"
Enter
Show
Sleep 350ms

# Home view first, then open the highlighted project (loghop-demo-recording)
Type "loghop tui --global"
Enter
Sleep 2600ms
Enter
Sleep 5200ms

# Move through the sessions so the table and preview pane are clearly visible
Type "j"
Sleep 1200ms
Type "j"
Sleep 1200ms
Type "k"
Sleep 1200ms

# Quit cleanly
Type "q"
Sleep 800ms
