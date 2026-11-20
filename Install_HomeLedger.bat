@echo off
setlocal
cd /d "%~dp0"
title Install HomeLedger
echo.
echo  Installing HomeLedger...
echo.

rem ---- find the Python launcher (pyw.exe = runs a program without a black window) ----
set "PYW="
set "PYARGS="
for /f "delims=" %%i in ('where pyw 2^>nul') do if not defined PYW set "PYW=%%i" & set "PYARGS=-3 "
if not defined PYW for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW goto nopython

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1" -Target "%PYW%" -Arguments "%PYARGS%\"%~dp0HomeLedger.pyw\""
if errorlevel 1 goto failed
echo.
echo  Done. Look for the HomeLedger icon on the Desktop and double-click it.
echo  Your accounts are stored in:  %LOCALAPPDATA%\HomeLedger
echo.
pause
exit /b 0

:nopython
echo  Python 3 was not found on this computer.
echo.
echo  Option 1: install Python from https://www.python.org/downloads/
echo            (on the first screen tick "Add python.exe to PATH"), then run this file again.
echo  Option 2: ask the person who set this up for the ready-made HomeLedger folder (it needs no Python).
echo.
pause
exit /b 1

:failed
echo.
echo  The icon could not be created. Please tell the person who set this up.
pause
exit /b 1
