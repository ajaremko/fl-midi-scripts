@echo off
rem Starts the MK2 bridge in a console window. Close the window (or Ctrl+C) to stop it.
rem Uses Python 3.12 through the py launcher: python-rtmidi only has ready-made Windows packages
rem up to 3.12, so a newer default Python would be missing it.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3.12 bridge.py %*
) else (
    python bridge.py %*
)
pause
