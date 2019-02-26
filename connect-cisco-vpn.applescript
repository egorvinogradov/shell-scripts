-- To assign a global shortcut, follow these instructions:
-- https://apple.stackexchange.com/a/247183

tell application "System Events"
  set CurrentClipboard to the clipboard as string
  set the clipboard to "$$$$$$$"                    -- replace $$$$$$$ w/ your password
  do shell script "scutil --nc start BostonGene"    -- replace BostonGene w/ your VPN service name from Network tab (see screenshot: https://i.imgur.com/jQK5DL9.png)
  delay 3

  tell application id "com.apple.systemevents"
    keystroke "v" using {command down}    -- emulate Cmd+V (paste copied password)
    keystroke (key code 36)               -- emulate Enter
  end tell
end tell
