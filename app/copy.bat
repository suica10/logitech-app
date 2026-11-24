@echo off
set PYTHONIOENCODING=utf-8
echo === copy start %DATE% %TIME% === > C:\Users\admin\logi\copy.log
C:\Users\admin\logi\venv\Scripts\python.exe C:\Users\admin\logi\app\copy_to_desktop.py >> C:\Users\admin\logi\copy.log 2>&1
echo DONE >> C:\Users\admin\logi\copy.log
