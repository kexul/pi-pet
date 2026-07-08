Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
WshShell.CurrentDirectory = Fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "python pet_app.py", 0, False
