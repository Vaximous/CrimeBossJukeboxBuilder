@echo off
rem Finds Python for the other .bat files. Sets PY.
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if defined PY %PY% -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>nul || set "PY="
if not defined PY (
    echo Python 3.9 or newer was not found.
    echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
    pause
    exit /b 1
)
exit /b 0
