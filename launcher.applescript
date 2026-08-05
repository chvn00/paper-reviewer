#!/usr/bin/env osascript
-- Paper Reviewer Launcher
-- Starts the FastAPI server and opens browser

tell application "Terminal"
    activate
    do script "/Users/cesarvalencia/Downloads/Paper_Reviewer_mac/launcher.sh"
end tell
