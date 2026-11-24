@echo off
set PYTHONIOENCODING=utf-8
echo === capture start %DATE% %TIME% === > C:\Users\admin\logi\capture.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\hidpp_capture.py >> C:\Users\admin\logi\capture.log 2>&1
echo DONE >> C:\Users\admin\logi\capture.log
