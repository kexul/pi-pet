Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\kkk\projects\pet"
WshShell.Run "uv run python pet_app.py", 0, False
