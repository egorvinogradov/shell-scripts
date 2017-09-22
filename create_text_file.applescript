----------------------------------------------------------------------------
--       Author: Christopher Stone 
--      Created: 2012-10-26 : 01:27
--     Modified: 2012-10-26 : 18:26
--  Application: Finder
--      Purpose: Create a new file from a file-type list in the front Finder window using
--             : template files stored in a folder.
-- Dependencies: Template files provided by the user.
--    Templates: Auto-creates a Text template - others are for the user to supply.
----------------------------------------------------------------------------

try

  try
    set templateFolderPath to ((path to application support from user domain as text) & "Script_Support:New_File_Here!:")
    set templateFolder to alias templateFolderPath
  on error
    set newFilesHereFolder to quoted form of (POSIX path of templateFolderPath)
    set textTemplate to newFilesHereFolder & "Text_Template.txt"
    do shell script "mkdir -p " & newFilesHereFolder & ";
     touch " & textTemplate & ";
     open -R " & textTemplate
    return
  end try

  tell application "Finder"
    if front window exists then
      set winTarget to target of front window as alias
      set fileTemplateList to name of files of templateFolder

      set AppleScript's text item delimiters to (return & templateFolderPath)
      set itemsToCopy to paragraphs of ((templateFolder as text) & "Text_Template.txt")

      repeat with i in itemsToCopy
        set i's contents to i as alias
      end repeat

      set copiedFiles to duplicate itemsToCopy to winTarget
      select copiedFiles

    else
      error "No windows open in Finder!"
    end if
  end tell

on error e number n
  set e to e & return & return & "Num: " & n
  tell me to set dDlg to display dialog e with title "ERROR!" buttons {"Cancel", "Copy", "OK"} default button "OK"
  if button returned of dDlg = "Copy" then set the clipboard to e
end try