@echo off
echo === probe5 start %DATE% %TIME% === > C:\Users\admin\logi\run5.log
C:\Users\admin\logi\venv\Scripts\python.exe -m pip install -q hidapi >> C:\Users\admin\logi\run5.log 2>&1
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe5.py >> C:\Users\admin\logi\run5.log 2>&1
echo DONE >> C:\Users\admin\logi\run5.log
