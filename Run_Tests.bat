@echo off
cd /d "%~dp0"
py -3 -W ignore -I tests\test_core.py
py -3 -W ignore -I tests\test_integration.py
pause
