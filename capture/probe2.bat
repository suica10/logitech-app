@echo off
echo === probe2 start %DATE% %TIME% === > C:\Users\admin\logi\run2.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe2.py >> C:\Users\admin\logi\run2.log 2>&1
echo DONE >> C:\Users\admin\logi\run2.log
