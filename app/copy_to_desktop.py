import winreg, shutil, os
with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as k:
    desktop, _ = winreg.QueryValueEx(k, "Desktop")
print("shell desktop =", desktop, flush=True)
src = r"C:\Users\admin\Desktop\LogiApp.bat"
dst = os.path.join(desktop, "LogiApp.bat")
shutil.copyfile(src, dst)
print("copied ->", dst, os.path.getsize(dst), "bytes", flush=True)
