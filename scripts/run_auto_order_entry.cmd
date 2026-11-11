@echo off
setlocal
cd /d "%~dp0.."
".venv\Scripts\python.exe" "scripts\auto_order_entry.py" %*
endlocal
