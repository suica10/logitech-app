@echo off
set PYTHONIOENCODING=utf-8
echo === probe11 start %DATE% %TIME% === > C:\Users\admin\logi\app\probe11.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\probe11.py >> C:\Users\admin\logi\app\probe11.log 2>&1
echo EXITCODE=%ERRORLEVEL% >> C:\Users\admin\logi\app\probe11.log
echo DONE >> C:\Users\admin\logi\app\probe11.log
