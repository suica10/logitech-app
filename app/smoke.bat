@echo off
set PYTHONIOENCODING=utf-8
echo === smoke start %DATE% %TIME% === > C:\Users\admin\logi\app\smoke.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\app.py --dry-run --seconds 20 >> C:\Users\admin\logi\app\smoke.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> C:\Users\admin\logi\app\smoke.log
echo DONE >> C:\Users\admin\logi\app\smoke.log
