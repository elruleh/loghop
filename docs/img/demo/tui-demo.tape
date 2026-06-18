# loghop TUI demo - stable version
# Output: loghop-tui-demo.mp4

Output loghop-tui-demo.mp4

Set Shell bash
Set FontSize 16
Set Width 1280
Set Height 720
Set Padding 24
Set Theme "Dracula"
Set TypingSpeed 16ms
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
Sleep 400ms

# Launch directly into the project screen (stable, no search step)
Type "loghop tui"
Enter
Sleep 3200ms

# Show the built-in help overlay
Type "?"
Sleep 1400ms
Escape
Sleep 600ms

# Back to home, then quit
Type "b"
Sleep 1100ms
Type "q"
Sleep 900ms
