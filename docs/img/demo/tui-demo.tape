# loghop TUI demo
# Output: loghop-tui-demo.mp4

Output loghop-tui-demo.mp4

Set Shell bash
Set FontSize 16
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 18ms
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
Sleep 500ms

Type "loghop tui --global"
Enter
Sleep 2500ms

# Search for the demo project and open it
Type "/"
Type "loghop-demo-recording"
Enter
Sleep 1200ms
Enter
Sleep 2200ms

# Show help overlay, then close it
Type "?"
Sleep 1500ms
Escape
Sleep 800ms

# Go back to the home list and quit
Type "b"
Sleep 1000ms
Type "q"
Sleep 1000ms
