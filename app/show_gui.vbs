Set wmi = GetObject("winmgts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("SELECT * FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe'")
running = False
For Each p In procs
  If InStr(p.CommandLine, "app.py") > 0 Then running = True
Next
Set fso = CreateObject("Scripting.FileSystemObject")
Set f = fso.CreateTextFile("C:\Users\admin\logi\app\show_gui.flag", True)
f.Close
If Not running Then
  Set sh = CreateObject("WScript.Shell")
  sh.CurrentDirectory = "C:\Users\admin\logi\app"
  sh.Run """C:\Users\admin\logi\venv\Scripts\python.exe"" ""C:\Users\admin\logi\app\app.py""", 0, False
End If
