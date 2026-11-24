@echo off
echo === probe3 start %DATE% %TIME% === > C:\Users\admin\logi\run3.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe3.py >> C:\Users\admin\logi\run3.log 2>&1
echo DONE >> C:\Users\admin\logi\run3.log
