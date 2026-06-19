# loghop TUI demo - real Textual interface with seeded projects
# Output: loghop-tui-demo.mp4
# Strategy: launch the real `loghop tui` (Textual, alt-screen) against a
# seeded workspace of six projects. VHS captures the alt-screen directly.
# Navigation: home -> arrow down -> enter a project -> browse sessions ->
# escape back -> quit. Runs against the editable venv build (the public
# 0.2.0 wheel has a project-list regression fixed in the unreleased src).

Output loghop-tui-demo.mp4

Set Shell bash
Set FontSize 16
Set Width 1280
Set Height 720
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 10ms
Set Framerate 30
Set WindowBar "Rings"
Set WindowBarSize 36

# Setup env (hidden, fast): editable loghop on PATH, seeded workspace
Hide
Type "export PATH=/home/user/projects/loghop/.venv/bin:$HOME/.local/bin:$PATH"
Enter
Type "cd /tmp"
Enter
Type "clear"
Enter
Show
Sleep 300ms

# Launch the TUI — home shows six real projects
Type "loghop tui"
Enter
Sleep 3.2s

# Move selection down to highlight a different project
Down
Sleep 700ms
Down
Sleep 700ms
Down
Sleep 700ms

# Enter the selected project to see its session timeline
Enter
Sleep 3.2s

# Browse the sessions
Down
Sleep 600ms
Down
Sleep 600ms

# Return to the project list
Escape
Sleep 1.2s

# Quit the TUI
Type "q"
Sleep 500ms
