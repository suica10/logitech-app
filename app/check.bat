@echo off
set PYTHONIOENCODING=utf-8
echo === check start %DATE% %TIME% === > C:\Users\admin\logi\check.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\check_config.py >> C:\Users\admin\logi\check.log 2>&1
echo DONE >> C:\Users\admin\logi\check.log
