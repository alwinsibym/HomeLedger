@echo off
cd /d "%~dp0"
title HomeLedger - send code to GitHub
echo HomeLedger - send the program code to GitHub in small steps
echo (your accounting data is never uploaded)
echo.
set PYCMD=
where py >nul 2>nul && set PYCMD=py
if not defined PYCMD where python >nul 2>nul && set PYCMD=python
if not defined PYCMD (
  echo Python was not found on this computer.
  echo.
  pause
  exit /b 1
)
%PYCMD% tools\push_in_batches.py %*
echo.
echo Finished. You can close this window.
pause
