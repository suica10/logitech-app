@echo off
echo === probe4 start %DATE% %TIME% === > C:\Users\admin\logi\run4.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_probe4.py >> C:\Users\admin\logi\run4.log 2>&1
echo DONE >> C:\Users\admin\logi\run4.log
