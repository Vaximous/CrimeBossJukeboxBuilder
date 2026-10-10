@echo off
rem Builds the Wwise project for every mod in Songs\ (or for the folder you drag onto this file).
cd /d "%~dp0"
call "%~dp0_python.cmd" || exit /b 1
%PY% -m jukebox_builder wwise %*
pause
