@echo off
echo === probe6 start %DATE% %TIME% === > C:\Users\admin\logi\run6.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe6.py >> C:\Users\admin\logi\run6.log 2>&1
echo DONE >> C:\Users\admin\logi\run6.log
