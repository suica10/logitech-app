@echo off
set PY=C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe
echo === setup start %DATE% %TIME% === > C:\Users\admin\logi\run.log
rmdir /S /Q C:\Users\admin\logi\venv >> C:\Users\admin\logi\run.log 2>&1
"%PY%" -m venv C:\Users\admin\logi\venv >> C:\Users\admin\logi\run.log 2>&1
C:\Users\admin\logi\venv\Scripts\python.exe -m pip install -q pywinusb >> C:\Users\admin\logi\run.log 2>&1
C:\Users\admin\logi\venv\Scripts\python.exe -c "import pywinusb; print('pywinusb ok')" >> C:\Users\admin\logi\run.log 2>&1
echo === probe === >> C:\Users\admin\logi\run.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe_win.py >> C:\Users\admin\logi\run.log 2>&1
echo DONE >> C:\Users\admin\logi\run.log
