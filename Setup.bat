@echo off
cd /d "%~dp0"
call "%~dp0_python.cmd" || exit /b 1
%PY% -m jukebox_builder setup
pause
