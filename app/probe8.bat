@echo off
set PYTHONIOENCODING=utf-8
echo === probe8 start %DATE% %TIME% === > C:\Users\admin\logi\app\probe8.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\probe8.py >> C:\Users\admin\logi\app\probe8.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> C:\Users\admin\logi\app\probe8.log
echo DONE >> C:\Users\admin\logi\app\probe8.log
