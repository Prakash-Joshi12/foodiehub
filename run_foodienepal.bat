@echo off
cd /d "%~dp0"
py -3.14 -m pip install -r requirements.txt
py -3.14 server.py
pause
