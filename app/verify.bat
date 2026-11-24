@echo off
set PYTHONIOENCODING=utf-8
echo === verify start %DATE% %TIME% === > C:\Users\admin\logi\app\verify.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\verify.py >> C:\Users\admin\logi\app\verify.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> C:\Users\admin\logi\app\verify.log
echo DONE >> C:\Users\admin\logi\app\verify.log
